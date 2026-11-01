"""Real POGEMA episodes with production planners, recorder, and offline monitors.

Small deterministic fixtures establish behavior, not research performance. They
do not replace the centralized oracle, matched sweeps, or statistical validation.
"""

import json
import unittest

from pogema import GridConfig, SumOfCostsAndMakespanMetric, pogema_v0

from decentralized_mapf import (
    DCMAPFPlanner, GlobalCommunication, IndependentAStar, KNNCommunication, Metrics,
    NoCommunication, PerfectChannel, RangeCommunication, run_episode,
)


class EpisodeIntegrationTests(unittest.TestCase):
    def episode(self, comm=None, *, planner_cls=DCMAPFPlanner, limit=20,
                horizon=20, starts=None, goals=None, grid=".....\n.....",
                with_cost_wrapper=True):
        starts = starts or [[0, 1], [0, 2]]
        goals = goals or [[0, 4], [0, 0]]
        config = GridConfig(map=grid, agents_xy=starts, targets_xy=goals,
                            num_agents=len(starts), obs_radius=2, seed=7,
                            max_episode_steps=horizon, observation_type="POMAPF",
                            on_target="finish", collision_system="priority", integration=None)
        env = pogema_v0(grid_config=config)
        if with_cost_wrapper:
            env = SumOfCostsAndMakespanMetric(env)
        self.addCleanup(env.close)
        env.reset(seed=7)
        fixed_goals = env.unwrapped.get_targets_xy(ignore_borders=True)
        planner = planner_cls(env.unwrapped.get_obstacles(ignore_borders=True), fixed_goals,
                              moves=config.MOVES)
        metrics = Metrics(fixed_goals, seed=7, window=3,
                          intent_provider=planner.intended_steps)
        result = run_episode(env, comm or GlobalCommunication(), PerfectChannel(),
                             planner, metrics, max_steps=limit)
        return result, metrics, planner, env

    def test_head_on_with_open_detour_finishes_under_global(self):
        result, metrics, _, _ = self.episode()
        self.assertEqual((result["ISR"], result["CSR"]), (1.0, 1.0))
        self.assertGreater(result["n_messages"], 0)
        self.assertGreaterEqual(result["rho_safe"], 0)
        self.assertEqual(result["rho_reach_mean"], 0)
        self.assertEqual(result["n_deadlocked"], 0)
        self.assertEqual(len(metrics.trace), result["steps"] + 1)

    def test_same_instance_without_messages_stalls_and_diagnoses_absence(self):
        result, metrics, _, _ = self.episode(NoCommunication())
        self.assertEqual(result["CSR"], 0.0)
        self.assertEqual(result["n_messages"], 0)
        self.assertEqual(result["n_deadlocked"], 2)
        self.assertEqual(result["n_epistemic"], 2)
        self.assertEqual(result["pct_epistemic"], 1.0)
        self.assertIsNone(result["makespan"])
        self.assertEqual(metrics.trace[0].positions, [(0, 1), (0, 2)])
        saved = json.loads(json.dumps({"summary": result, "raw": metrics.to_data()}))
        self.assertEqual(Metrics.from_data(saved["raw"]).summary(), saved["summary"])

    def test_known_arrival_costs(self):
        result, _, _, _ = self.episode(planner_cls=IndependentAStar,
                                       starts=[[0, 0], [0, 4]], goals=[[0, 1], [0, 2]])
        self.assertEqual((result["makespan"], result["SoC"]), (2, 3))
        self.assertEqual(result["environment_metrics"]["ep_length"], 1.5)

    def test_staggered_arrival_costs(self):
        for distances in ((1, 2), (1, 3), (1, 4), (2, 5), (1, 3, 6), (2, 4, 7),
                          (0, 4), (0, 0)):
            with self.subTest(arrival_steps=distances):
                starts = [[i, 0] for i in range(len(distances))]
                goals = [[i, d] for i, d in enumerate(distances)]
                grid = "\n".join(["........"] * len(distances))
                result, metrics, _, _ = self.episode(
                    NoCommunication(), planner_cls=IndependentAStar,
                    starts=starts, goals=goals, grid=grid,
                )
                self.assertEqual((result["ISR"], result["CSR"]), (1.0, 1.0))
                self.assertEqual(result["SoC"], sum(distances))
                self.assertEqual(result["makespan"], max(distances))
                saved = json.loads(json.dumps({"summary": result, "raw": metrics.to_data()}))
                self.assertEqual(Metrics.from_data(saved["raw"]).summary(), saved["summary"])
                self.assertNotIn(result["steps"], metrics.intents)

    def test_costs_without_native_wrapper(self):
        result, _, _, _ = self.episode(
            NoCommunication(), planner_cls=IndependentAStar, grid=".....\n.....",
            starts=[[0, 0], [1, 0]], goals=[[0, 1], [1, 4]], with_cost_wrapper=False,
        )
        self.assertEqual((result["SoC"], result["makespan"]), (5, 4))
        self.assertNotIn("SoC", result["environment_metrics"])

    def test_corridor_deadlock(self):
        result, _, _, _ = self.episode(grid=".....")
        self.assertEqual(result["CSR"], 0.0)
        self.assertEqual(result["n_rule_failure"], 2)
        self.assertEqual(result["n_epistemic"], 0)
        self.assertGreaterEqual(result["rho_safe"], 0)

         # Mutual claim receipt does not imply physical conflict resolution.
        self.assertEqual(result["e5"]["n_conflicts"], 1)
        self.assertEqual(result["e5"]["n_agreed"], 1)
        self.assertEqual(result["e5"]["agreement_coverage"], 1.0)
        self.assertEqual(result["e5"]["mean_rounds_to_agreement"], 0)
        self.assertEqual(result["e5"]["episodes"][0]["outcome"], "agreed")
        self.assertIsNone(result["e5"]["episodes"][0]["ended_at"])

    def test_all_topologies_use_the_same_planner_and_seeded_initial_state(self):
        states = []
        for comm in (GlobalCommunication(), NoCommunication(), RangeCommunication(0),
                     RangeCommunication(10), KNNCommunication(1)):
            with self.subTest(topology=type(comm).__name__):
                result, metrics, _, _ = self.episode(comm)
                states.append(metrics.trace[0].positions)
                expected_solved = not isinstance(comm, NoCommunication) and not (
                    isinstance(comm, RangeCommunication) and comm.r == 0)
                self.assertEqual(result["CSR"], float(expected_solved))
        self.assertTrue(all(state == states[0] for state in states))

    def test_caller_cutoff_and_zero_steps_preserve_unknown_wrapper_metrics(self):
        for limit in (0, 1):
            with self.subTest(limit=limit):
                result, metrics, _, _ = self.episode(limit=limit)
                self.assertEqual(result["steps"], limit)
                self.assertIsNone(result["ISR"])
                self.assertIsNone(result["SoC"])
                self.assertIsNone(result["rho_live_mean"])
                self.assertEqual(len(metrics.trace), limit + 1)
                self.assertEqual(len(metrics.e5.rounds), limit)
                self.assertNotIn(limit, metrics.intents)
                self.assertNotIn(limit, metrics.to_data()["intents"])

    def test_reset_and_json_roundtrip(self):
        result, metrics, planner, env = self.episode()
        restored = Metrics.from_data(json.loads(json.dumps(metrics.to_data())))
        self.assertEqual(restored.summary(), result)
        next_metrics = Metrics(planner.goals, seed=7, window=3,
                               intent_provider=planner.intended_steps)
        repeated = run_episode(env, GlobalCommunication(), PerfectChannel(),
                               planner, next_metrics, 20)
        self.assertEqual(repeated, result)
        self.assertEqual(next_metrics.trace, metrics.trace)

    def test_e5_instrumentation_does_not_change_trajectory(self):
        # Reference run: E5 instrumentation enabled.
        result_a, metrics_a, _, _ = self.episode()

        # Second run: same environment and seed, but hide the optional E5 hooks.
        class MetricsWithoutE5:
            def __init__(self, recorder):
                self.recorder = recorder

            def __getattr__(self, name):
                if name in ("capture_e5_round", "finalize_e5"):
                    raise AttributeError(name)
                return getattr(self.recorder, name)

        starts = [[0, 1], [0, 2]]
        goals = [[0, 4], [0, 0]]

        config = GridConfig(
            map=".....\n.....",
            agents_xy=starts,
            targets_xy=goals,
            num_agents=2,
            obs_radius=2,
            seed=7,
            max_episode_steps=20,
            observation_type="POMAPF",
            on_target="finish",
            collision_system="priority",
            integration=None,
        )
        env = pogema_v0(grid_config=config)
        self.addCleanup(env.close)
        env.reset(seed=7)

        fixed_goals = env.unwrapped.get_targets_xy(ignore_borders=True)
        planner = DCMAPFPlanner(
        env.unwrapped.get_obstacles(ignore_borders=True),
        fixed_goals,
        moves=config.MOVES,
    )
        recorder = Metrics(
        fixed_goals,
        seed=7,
        window=3,
        intent_provider=planner.intended_steps,
    )

        result_b = run_episode(
        env,
        GlobalCommunication(),
        PerfectChannel(),
        planner,
        MetricsWithoutE5(recorder),
        max_steps=20,
    )

        self.assertEqual(
        [row.positions for row in metrics_a.trace],
        [row.positions for row in recorder.trace],
    )
        self.assertEqual(result_a["CSR"], result_b["CSR"])
        self.assertEqual(result_a["ISR"], result_b["ISR"])
        self.assertEqual(result_a["steps"], result_b["steps"])


if __name__ == "__main__":
    unittest.main()
