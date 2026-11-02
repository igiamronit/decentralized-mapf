"""Planner decisions without simulator arbitration, using only own state and inbox."""

from collections import deque
import unittest

from decentralized_mapf import DCMAPFPlanner, IndependentAStar, Message
from decentralized_mapf.pathfinding import astar
from decentralized_mapf.planner import blocking_neighbour


class PlannerTests(unittest.TestCase):
    def prepare(self, cls=DCMAPFPlanner, position=(1, 0), goal=(1, 2), agent_id=1):
        planner = cls([[0] * 3 for _ in range(3)], [goal, goal])
        planner.observe(agent_id, {"xy": (0, 0)}, position, goal)
        planner.compose(agent_id, 0)
        return planner

    def test_astar_shortest_path_against_breadth_first_search(self):
        grid = [[0, 0, 0, 0], [0, 1, 1, 0], [0, 0, 0, 0]]
        for start in ((0, 0), (0, 3), (2, 1)):
            for goal in ((0, 2), (2, 0), (2, 3)):
                with self.subTest(start=start, goal=goal):
                    queue, seen = deque([(start, 0)]), {start}
                    while queue:
                        cell, distance = queue.popleft()
                        if cell == goal:
                            break
                        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                            nxt = (cell[0] + dr, cell[1] + dc)
                            r, c = nxt
                            if 0 <= r < 3 and 0 <= c < 4 and not grid[r][c] and nxt not in seen:
                                seen.add(nxt)
                                queue.append((nxt, distance + 1))
                    path = astar(grid, start, goal)
                    self.assertEqual(len(path), distance)
                    self.assertEqual(path[-1], goal)
                    for before, after in zip([start] + path, path):
                        self.assertEqual(abs(before[0] - after[0]) + abs(before[1] - after[1]), 1)
                        self.assertEqual(grid[after[0]][after[1]], 0)

    def test_unreachable_and_already_arrived_wait(self):
        planner = IndependentAStar([[0, 1, 0]], [(0, 2)])
        planner.observe(0, {}, (0, 0), (0, 2))
        self.assertEqual(planner.act(0, {}, [], (0, 2)), planner.moves.index((0, 0)))
        planner.observe(0, {}, (0, 2), (0, 2))
        self.assertEqual(planner.compose(0, 0).next_cells, [])
        self.assertEqual(astar([[0]], (0, 0), (0, 0)), [])

    def test_broadcast_snapshot(self):
        planner = self.prepare()
        message = planner.compose(1, 0)
        self.assertEqual((message.position, message.goal, message.next_cells[0], message.sent_at),
                         ((1, 0), (1, 2), (1, 1), 0))
        message.next_cells.clear()
        self.assertEqual(planner.paths[1], [(1, 1), (1, 2)])

    def test_path_follows_observed_position(self):
        planner = self.prepare()
        planner.act(1, {}, [], (1, 2))
        planner.observe(1, {}, (1, 0), (1, 2))  # rejected by the simulator
        self.assertEqual(planner.compose(1, 1).next_cells[0], (1, 1))
        planner.observe(1, {}, (1, 1), (1, 2))
        self.assertEqual(planner.compose(1, 2).next_cells, [(1, 2)])
        planner.observe(1, {}, (0, 0), (1, 2))  # unexpected displacement triggers replan
        self.assertEqual(len(planner.paths[1]), 3)

    def test_empty_inbox_matches_independent_astar(self):
        baseline, coordinated = self.prepare(IndependentAStar), self.prepare()
        self.assertEqual(baseline.act(1, {}, [], (1, 2)), coordinated.act(1, {}, [], (1, 2)))

    def test_priority_is_independent_of_inbox_order(self):
        planner = self.prepare(agent_id=1)
        messages = [Message(2, (2, 1), (0, 1), [(1, 1)]),
                    Message(0, (0, 1), (2, 1), [(1, 1)])]
        for inbox in (messages, messages[::-1]):
            self.assertEqual(planner.act(1, {}, inbox, (1, 2)), planner.moves.index((0, 0)))
        winner = self.prepare(agent_id=0)
        self.assertEqual(winner.act(0, {}, [messages[0]], (1, 2)), winner.moves.index((0, 1)))

    def test_occupied_cell_and_swap_are_distinct_from_empty_contention(self):
        position, nxt = (1, 0), (1, 1)
        self.assertEqual(blocking_neighbour(0, position, nxt, [Message(1, nxt, (2, 2))]), 1)
        self.assertIsNone(blocking_neighbour(0, position, nxt,
                                            [Message(1, nxt, (2, 2), [(1, 2)])]))
        self.assertEqual(blocking_neighbour(0, position, nxt,
                                            [Message(1, nxt, (2, 2), [position])]), 1)

    def test_head_on_priority(self):
        loser = self.prepare(position=(1, 1), goal=(1, 0))
        action = loser.act(1, {}, [Message(0, (1, 0), (1, 2), [(1, 1)])], (1, 0))
        self.assertIn(loser.moves[action], ((-1, 0), (1, 0)))
        winner = self.prepare(position=(1, 0), agent_id=0)
        action = winner.act(0, {}, [Message(1, (1, 1), (1, 0), [(1, 0)])], (1, 2))
        self.assertEqual(winner.moves[action], (0, 0))

    def test_blocked_swap_and_reset(self):
        planner = DCMAPFPlanner([[0, 0, 0]], [(0, 2), (0, 0)])
        planner.observe(1, {}, (0, 1), (0, 0))
        planner.compose(1, 0)
        inbox = [Message(0, (0, 0), (0, 2), [(0, 1)])]
        action = planner.act(1, {}, inbox, (0, 0))
        self.assertEqual(planner.moves[action], (0, 0))
        planner.reset()
        self.assertEqual((planner.paths, planner.positions, planner._yield_to), ({}, {}, {}))

    def test_stale_messages_are_ignored(self):
        planner = self.prepare()
        planner.compose(1, 2)
        action = planner.act(1, {}, [Message(0, (0, 1), (2, 1), [(1, 1)], sent_at=1)], (1, 2))
        self.assertEqual(planner.moves[action], (0, 1))

    def test_retreat_does_not_enter_an_occupied_pocket(self):
        grid = [[0] * 5, [1, 1, 1, 0, 1]]
        planner = DCMAPFPlanner(grid, [(0, 4), (0, 0), (0, 3)])
        planner.observe(1, {}, (0, 2), (0, 0))
        planner.compose(1, 0)
        inbox = [Message(0, (0, 1), (0, 4), [(0, 2), (0, 3), (0, 4)]),
                 Message(2, (1, 3), (0, 3), [(1, 3)])]
        action = planner.act(1, {}, inbox, (0, 0))
        self.assertEqual(planner.moves[action], (0, 0))

    def test_retreat_plan_survives_a_rejected_move(self):
        grid = [[0] * 5, [1, 1, 1, 0, 1]]
        planner = DCMAPFPlanner(grid, [(0, 4), (0, 0)])
        planner.observe(1, {}, (0, 2), (0, 0))
        planner.compose(1, 0)
        inbox = [Message(0, (0, 1), (0, 4), [(0, 2), (0, 3), (0, 4)])]
        self.assertEqual(planner.moves[planner.act(1, {}, inbox, (0, 0))], (0, 1))
        planner.observe(1, {}, (0, 2), (0, 0))
        self.assertEqual(planner.compose(1, 1).next_cells, [(0, 3), (1, 3)])

    def test_losing_peer_receipt_releases_retreat_immediately(self):
        grid = [[0] * 5, [1, 1, 1, 0, 1]]
        for inbox_kind in ("empty", "stale_peer", "another_robot"):
            with self.subTest(inbox=inbox_kind):
                planner = DCMAPFPlanner(grid, [(0, 4), (0, 0), (0, 4)])
                planner.observe(1, {}, (0, 2), (0, 0))
                planner.compose(1, 0)
                peer = Message(0, (0, 1), (0, 4), [(0, 2), (0, 3), (0, 4)])
                self.assertEqual(planner.moves[planner.act(1, {}, [peer], (0, 0))], (0, 1))
                planner.observe(1, {}, (0, 3), (0, 0))
                planner.compose(1, 1)
                inbox = {"empty": [], "stale_peer": [peer], "another_robot": [
                    Message(2, (0, 4), (0, 4), sent_at=1)
                ]}[inbox_kind]
                # Resume the goal route, rather than taking the old refuge step down.
                action = planner.act(1, {}, inbox, (0, 0))
                self.assertEqual(planner.moves[action], (0, -1))
                self.assertNotIn(1, planner._yield_to)
                self.assertNotIn(1, planner._refuges)

    def test_custom_action_order_and_invalid_configuration(self):
        moves = [(0, 1), (0, -1), (1, 0), (-1, 0), (0, 0)]
        planner = IndependentAStar([[0, 0]], [(0, 1)], moves=moves)
        planner.observe(0, {}, (0, 0), (0, 1))
        self.assertEqual(planner.act(0, {}, [], (0, 1)), 0)
        for grid, goals, extra in (([], [], {}), ([[0], [0, 0]], [], {}),
                                   ([[0]], [(1, 0)], {}), ([[1]], [(0, 0)], {}),
                                   ([[0]], [(0, 0)], {"moves": [(0, 0)]})):
            with self.subTest(grid=grid, goals=goals), self.assertRaises(ValueError):
                IndependentAStar(grid, goals, **extra)


if __name__ == "__main__":
    unittest.main()
