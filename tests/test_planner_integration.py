"""Planner episodes using real POGEMA and the existing test recorder."""

import unittest

from pogema import GridConfig, pogema_v0

from decentralized_mapf import (
    DCMAPFPlanner, GlobalCommunication, NoCommunication, PerfectChannel, run_episode,
)
from test_runner import RecordingMetrics


class PlannerIntegrationTests(unittest.TestCase):
    def episode(self, grid, starts, goals, *, comm=None, planner=None):
        config = GridConfig(
            map=grid, num_agents=len(starts), agents_xy=starts, targets_xy=goals,
            seed=7, obs_radius=2, max_episode_steps=30,
            observation_type="POMAPF", on_target="finish",
            collision_system="priority", integration=None,
        )
        env = pogema_v0(grid_config=config)
        self.addCleanup(env.close)
        env.reset(seed=7)
        if planner is None:
            planner = DCMAPFPlanner(env.unwrapped.get_obstacles(ignore_borders=True),
                                   goals, moves=config.MOVES)
        recorder = RecordingMetrics()
        result = run_episode(env, comm or GlobalCommunication(), PerfectChannel(),
                             planner, recorder, max_steps=30)
        # Finished coordinates persist, but finished robots no longer occupy cells.
        active = set(range(len(goals)))
        for row in recorder.trace:
            active = {i for i in active if row.positions[i] != tuple(goals[i])}
            self.assertEqual(len({row.positions[i] for i in active}), len(active))
        return result, recorder.trace, planner

    def test_retreat_to_pocket(self):
        result, trace, _ = self.episode(".....\n###.#", [(0, 1), (0, 2)], [(0, 4), (0, 0)])
        self.assertEqual(trace[-1].positions, [(0, 4), (0, 0)])
        self.assertLess(result["steps"], 30)
        self.assertEqual(trace[1].positions[1], (0, 3))
        self.assertIn((1, 3), [row.positions[1] for row in trace])

    def test_vertical_and_reversed_corridors(self):
        fixtures = [
            (".....\n#.###", [(0, 3), (0, 2)], [(0, 0), (0, 4)], (1, 1)),
            (".#\n.#\n.#\n..\n.#", [(1, 0), (2, 0)], [(4, 0), (0, 0)], (3, 1)),
        ]
        for grid, starts, goals, pocket in fixtures:
            with self.subTest(grid=grid):
                _, trace, _ = self.episode(grid, starts, goals)
                self.assertEqual(trace[-1].positions, goals)
                self.assertIn(pocket, [row.positions[1] for row in trace])

    def test_distant_pocket_and_waiting_for_peer_to_pass(self):
        result, trace, _ = self.episode(".......\n#####.#", [(0, 1), (0, 2)], [(0, 6), (0, 0)])
        self.assertEqual(trace[-1].positions, [(0, 6), (0, 0)])
        self.assertLess(result["steps"], 30)
        pocket_steps = [row.t for row in trace if row.positions[1] == (1, 5)]
        self.assertGreaterEqual(len(pocket_steps), 2)
        for t in pocket_steps[:-1]:
            self.assertLessEqual(trace[t].positions[0][1], 5)

    def test_adjacent_pocket(self):
        _, trace, _ = self.episode(".....\n##.##", [(0, 1), (0, 2)], [(0, 4), (0, 0)])
        self.assertEqual(trace[-1].positions, [(0, 4), (0, 0)])
        self.assertIn((1, 2), [row.positions[1] for row in trace])

    def test_no_messages_and_no_passing_space(self):
        for grid, comm in ((".....\n###.#", NoCommunication()),
                           (".....", GlobalCommunication())):
            with self.subTest(grid=grid, comm=type(comm).__name__):
                result, trace, _ = self.episode(grid, [(0, 1), (0, 2)], [(0, 4), (0, 0)], comm=comm)
                self.assertEqual(result["steps"], 30)
                self.assertTrue(all(row.positions == [(0, 1), (0, 2)] for row in trace))

    def test_reset_after_retreat(self):
        args = (".....\n###.#", [(0, 1), (0, 2)], [(0, 4), (0, 0)])
        first_result, first_trace, planner = self.episode(*args)
        result, trace, _ = self.episode(*args, planner=planner)
        self.assertEqual((result, trace), (first_result, first_trace))


if __name__ == "__main__":
    unittest.main()
