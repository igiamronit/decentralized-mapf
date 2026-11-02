"""Independent A* and deterministic local priority/yield coordination.

This implements the build guide's simplified A* plus yield design, not a verified
reproduction of the complete published DCMAPF algorithm. Static obstacle knowledge
is shared a priori; robot state is private except for delivered messages. Neither
planner reads another robot's cache, the communication model, or metric values.
"""

from collections import deque

from .interfaces import Message, Planner
from .pathfinding import astar, free_neighbours


def blocking_neighbour(agent_id, position, next_cell, neighbours):
    """Identify a local blocker from supplied messages, with stable ID ties.

    An occupant blocks a cell unless it advertises a move out (not a swap).
    For an empty contested cell the smaller robot ID wins. A swap is blocked
    regardless of priority: waiting alone cannot exchange occupied cells.
    Used by the planner on its inbox and offline diagnostics on recorded claims.
    """
    blockers = []
    for msg in neighbours:
        if msg.sender == agent_id:
            continue
        other_pos = tuple(msg.position)
        other_next = tuple(msg.next_cells[0]) if msg.next_cells else other_pos
        occupied = other_pos == next_cell and other_next in (other_pos, position)
        contested = other_next == next_cell and msg.sender < agent_id
        if occupied or contested:
            blockers.append(msg.sender)
    return min(blockers, default=None)


class IndependentAStar(Planner):
    """Static-map A* baseline; messages never affect actions.

    Supply the borderless static map (0 free, nonzero obstacle), fixed goals in
    stable ID order, and GridConfig().MOVES. Paths are advanced only after observe
    confirms actual movement, so rejected moves do not corrupt future broadcasts.
    POGEMA observations remain start-relative; supplied own positions are the
    authority for shared coordinates. No global robot positions are accepted.
    """

    def __init__(self, grid_map, goals, *, moves=None):
        self.grid_map = tuple(tuple(bool(cell) for cell in row) for row in grid_map)
        if not self.grid_map or not self.grid_map[0] or any(
            len(row) != len(self.grid_map[0]) for row in self.grid_map
        ):
            raise ValueError("grid_map must be a nonempty rectangle")
        self.goals = tuple(tuple(goal) for goal in goals)
        # POGEMA's standard ordering. Custom configurations must pass MOVES.
        self.moves = tuple(tuple(move) for move in (moves if moves is not None else
                           ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1))))
        if len(self.moves) != 5 or set(self.moves) != {
            (0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)
        }:
            raise ValueError("moves must contain wait and the four cardinal moves once")
        for goal in self.goals:
            self._check_cell(goal)
        self.reset()

    def _check_cell(self, cell):
        r, c = cell
        if not (0 <= r < len(self.grid_map) and 0 <= c < len(self.grid_map[0])):
            raise ValueError("Position/goal is outside the static map")
        if self.grid_map[r][c]:
            raise ValueError("Position/goal is a static obstacle")

    def reset(self):
        """Discard every episode's paths, observations, and local yield state."""
        self.positions, self.paths = {}, {}

    def observe(self, agent_id, observation, position, goal):
        position, goal = tuple(position), tuple(goal)
        if goal != self.goals[agent_id]:
            raise ValueError("Runner goal differs from configured fixed goal")
        self._check_cell(position)
        previous = self.positions.get(agent_id)
        path = self.paths.get(agent_id, [])
        if previous != position:
            if path and path[0] == position:
                path = path[1:]
            else:
                path = []
        if not path and position != goal:
            path = astar(self.grid_map, position, goal)
        self.positions[agent_id], self.paths[agent_id] = position, path

    def compose(self, agent_id, t):
        """Broadcast the current uncoordinated plan, before inbox-based yielding."""
        return Message(agent_id, self.positions[agent_id], self.goals[agent_id],
                       list(self.paths[agent_id][:3]), sent_at=t)

    def intended_steps(self):
        """Copy pre-decision intentions for a recorder; never consumed by act()."""
        return {i: path[0] if path else self.positions[i]
                for i, path in self.paths.items()}

    def _action(self, position, next_cell):
        return self.moves.index((next_cell[0] - position[0], next_cell[1] - position[1]))

    def act(self, agent_id, observation, inbox, goal):
        path, position = self.paths[agent_id], self.positions[agent_id]
        return self._action(position, path[0] if path else position)


class DCMAPFPlanner(IndependentAStar):
    """One fixed planner for every topology: A* plus lower-ID-first yielding.

    The lower-priority agent waits on cell contention. On a head-on swap, it
    tries a detour to its goal, then a route to the nearest off-axis refuge. That
    route may start by retreating along the corridor. It waits in the refuge
    until an unreserved route to the goal opens or the peer leaves its inbox.
    No completeness or deadlock-freedom guarantee is implied by this local rule.

    Only current-step messages are acted on. Stale information needs an explicit
    policy before delayed-message experiments.
    """

    def reset(self):
        super().reset()
        self._times, self._yield_to, self._refuges = {}, {}, {}

    def compose(self, agent_id, t):
        self._times[agent_id] = t
        return super().compose(agent_id, t)

    @staticmethod
    def has_priority(me, other):
        """A strict total order independent of topology, distance, or call order."""
        return me < other

    def act(self, agent_id, observation, inbox, goal):
        position = self.positions[agent_id]
        path = self.paths[agent_id]
        if not path:
            return self._action(position, position)
        # Delayed-message handling is outside the current planner contract.
        neighbours = sorted((m for m in inbox if m.sent_at == self._times[agent_id]),
                            key=lambda m: m.sender)
        peer = next((m for m in neighbours if m.sender == self._yield_to.get(agent_id)), None)
        if peer is not None:
            return self._avoid(agent_id, neighbours, peer)
        released_peer = self._yield_to.pop(agent_id, None)
        self._refuges.pop(agent_id, None)
        if released_peer is not None:
            # A refuge path is not a goal path. Releasing the peer must also
            # release that route, even halfway through a retreat. Recheck any
            # other current claims below before executing the new goal step.
            path = self.paths[agent_id] = astar(self.grid_map, position, goal)
            if not path:
                return self._action(position, position)
        blocker = blocking_neighbour(agent_id, position, path[0], neighbours)
        if blocker is None:
            return self._action(position, path[0])
        peer = next(m for m in neighbours if m.sender == blocker)
        swap = (tuple(peer.position) == path[0] and peer.next_cells
                and tuple(peer.next_cells[0]) == position)
        if swap and not self.has_priority(agent_id, blocker):
            self._yield_to[agent_id] = blocker
            return self._avoid(agent_id, neighbours, peer)
        return self._action(position, position)

    def _avoid(self, agent_id, neighbours, peer):
        """Use only inbox claims for a detour; never infer unseen robot occupancy."""
        position, goal = self.positions[agent_id], self.goals[agent_id]
        occupied = {tuple(m.position) for m in neighbours}
        reserved = occupied | {tuple(m.next_cells[0]) for m in neighbours if m.next_cells}
        detour = astar(self.grid_map, position, goal, blocked=reserved)
        if detour:
            self._yield_to.pop(agent_id, None)
            self._refuges.pop(agent_id, None)
            self.paths[agent_id] = detour
            return self._action(position, detour[0])

        refuge = self._refuges.get(agent_id)
        if refuge is None:
            escape = self._refuge_path(position, peer, reserved)
            if escape:
                refuge = self._refuges[agent_id] = escape[-1]
        else:
            escape = astar(self.grid_map, position, refuge, blocked=reserved)
        if refuge is not None and escape:
            self.paths[agent_id] = escape
            return self._action(position, escape[0])
        # Already in the refuge, or its route is temporarily blocked.
        self.paths[agent_id] = []
        return self._action(position, position)

    def _refuge_path(self, position, peer, reserved):
        """Find the nearest cell outside the original head-on row or column.

        Breadth-first search may retreat before entering a pocket. It uses only
        the known static map and received occupancy/claims. Future peer claims
        cannot be refuge destinations, but can be traversed before the peer gets
        there. Equal-length escapes follow the shared neighbour ordering.
        """
        horizontal = position[0] == peer.position[0]
        future_claims = {tuple(cell) for cell in peer.next_cells}
        parents = {position: None}
        pending = deque([position])
        while pending:
            cell = pending.popleft()
            off_axis = cell[0] != position[0] if horizontal else cell[1] != position[1]
            if off_axis and cell not in future_claims:
                path = []
                while cell != position:
                    path.append(cell)
                    cell = parents[cell]
                return path[::-1]
            for nxt in free_neighbours(self.grid_map, cell, reserved):
                if nxt not in parents:
                    parents[nxt] = cell
                    pending.append(nxt)
        return []
