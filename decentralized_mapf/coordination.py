"""Offline analysis of how robots coordinate when their claims conflict.

A conflict is read from the saved trace, intentions and chosen actions. It
records what the robot heard and how it responded. Like the monitors, this
runs after the episode and never feeds back into planning.

Grid moves change the shortest-path distance to a goal by exactly one cell,
because a four-connected grid is bipartite. So a move that does not follow
the robot's claim is either a detour (one cell closer) or a retreat (one cell
farther). These labels describe geometry, not the planner branch that chose it.
"""

from collections import deque

from .interfaces import Message
from .monitors import first_arrival
from .pathfinding import free_neighbours
from .planner import blocking_neighbour

RESPONSES = ("wait", "detour", "retreat", "proceed")


def goal_distances(grid_map, goal):
    """Shortest static-map distance from every reachable cell to the goal."""
    goal = tuple(goal)
    distances = {goal: 0}
    pending = deque([goal])
    while pending:
        cell = pending.popleft()
        for nxt in free_neighbours(grid_map, cell):
            if nxt not in distances:
                distances[nxt] = distances[cell] + 1
                pending.append(nxt)
    return distances


def respond(position, claim, chosen, distances):
    """Label the move a robot chose when its claimed cell was contested."""
    if chosen == position:
        return "wait"
    if chosen == claim:
        return "proceed"
    if distances[chosen] < distances[position]:
        return "detour"
    return "retreat"


def conflict_events(trace, intents, actions, goals, distances, moves):
    """List every decision where another robot's claim blocks a robot's claim.

    intents[t] holds pre-decision claimed cells and actions[t] the chosen
    action indices. The blocker is found from all claims, so a robot that
    never heard it still has a conflict. Its response comes from its own
    chosen action; rejected means the simulator refused that move.
    """
    events = []
    for t, row in enumerate(trace[:-1]):
        claims = intents.get(t, {})
        for i, claim in claims.items():
            position = tuple(row.positions[i])
            claim = tuple(claim)
            if claim == position:
                continue
            others = [Message(j, tuple(row.positions[j]), tuple(goals[j]), [tuple(cell)], sent_at=t)
                      for j, cell in claims.items() if j != i]
            blocker = blocking_neighbour(i, position, claim, others)
            if blocker is None:
                continue

            dr, dc = moves[actions[t][i]]
            chosen = (position[0] + dr, position[1] + dc)
            moved_to = tuple(trace[t + 1].positions[i])
            events.append({
                "t": t,
                "agent": i,
                "blocker": blocker,
                "has_priority": i < blocker,
                "heard": blocker in row.inbox_senders.get(i, []),
                "heard_back": i in row.inbox_senders.get(blocker, []),
                "response": respond(position, claim, chosen, distances[i]),
                "rejected": chosen != position and moved_to == position,
            })
    return events


def blocked_moves(trace, actions, moves):
    """Count decisions where a robot chose to move but stayed in place."""
    count = 0
    for t, chosen_actions in actions.items():
        for i, action in chosen_actions.items():
            if moves[action] != (0, 0) and trace[t + 1].positions[i] == trace[t].positions[i]:
                count += 1
    return count


def coordination_summary(trace, intents, actions, goals, distances, moves):
    """Per-run conflict, delay and arrival numbers, plus the conflict events.

    Delay is first arrival minus shortest path length: steps lost to other
    robots. It covers arrived robots only; unfinished robots appear in ISR.
    """
    moves = [tuple(move) for move in moves]
    events = conflict_events(trace, intents, actions, goals, distances, moves)

    arrivals = [first_arrival(trace, i, goals) for i in range(len(goals))]
    delays = [arrival - distances[i][tuple(trace[0].positions[i])]
              for i, arrival in enumerate(arrivals) if arrival is not None]

    summary = {
        "n_conflicts": len(events),
        "n_heard": sum(e["heard"] for e in events),
        "n_mutual": sum(e["heard"] and e["heard_back"] for e in events),
        "n_blocked_moves": blocked_moves(trace, actions, moves),
        "delay_mean": sum(delays) / len(delays) if delays else None,
        "delay_max": max(delays, default=None),
        "arrival_steps": arrivals,
    }
    for response in RESPONSES:
        summary[f"n_{response}_heard"] = sum(
            e["heard"] and e["response"] == response for e in events)
        summary[f"n_{response}_unheard"] = sum(
            not e["heard"] and e["response"] == response for e in events)
    return summary, events
