"""Analytic monitor traces: boundaries, unknowns, causality limits, and persistence."""

import json
import unittest

from decentralized_mapf import Message, Metrics, StepRecord
from decentralized_mapf import monitors


def trace(positions, heard=None):
    return [StepRecord(t, [tuple(p) for p in cells], 0.0, len(cells), 0,
                       heard or {i: [] for i in range(len(cells))})
            for t, cells in enumerate(positions)]


class MonitorTests(unittest.TestCase):
    def test_reach_shortfall_and_stall_margin(self):
        rows = trace([[(0, 0)], [(0, 1)], [(0, 2)], [(0, 2)], [(0, 2)]])
        goals = [(0, 5)]
        self.assertEqual(monitors.rho_reach(rows, 0, goals), -3)
        self.assertEqual(monitors.rho_live(rows, 0, goals, W=2), -1)
        self.assertEqual(monitors.stall_start(rows, 0, goals, W=2), 2)
        self.assertEqual(monitors.deadlocked_agents(rows, goals, W=2), {0})

    def test_eventual_arrival_is_not_deadlocked_and_finished_windows_are_excluded(self):
        rows = trace([[(0, 0)], [(0, 1)], [(0, 2)], [(0, 2)], [(0, 2)]])
        goals = [(0, 2)]
        self.assertEqual(monitors.rho_live(rows, 0, goals, W=2), 0)
        self.assertEqual(monitors.deadlocked_agents(rows, goals, W=2), set())
        self.assertEqual(monitors.rho_reach(rows, 0, goals), 0)

    def test_short_trace_is_unknown_and_full_window_at_boundary_is_evaluated(self):
        rows = trace([[(0, 0)]] * 3)
        self.assertIsNone(monitors.rho_live(rows, 0, [(0, 1)], W=3))
        self.assertEqual(monitors.deadlocked_agents(rows, [(0, 1)], W=3), set())
        self.assertEqual(monitors.rho_live(rows, 0, [(0, 1)], W=2), -1)
        for window in (0, -1, 1.5, True):
            with self.subTest(window=window), self.assertRaises(ValueError):
                monitors.rho_live(rows, 0, [(0, 1)], W=window)

    def test_eventual_progress_includes_interior_witness_and_zero_satisfies(self):
        rows = trace([[(0, 2)], [(0, 1)], [(0, 2)]])
        # Progress at the interior sample satisfies the stated eventual formula.
        self.assertEqual(monitors.rho_live(rows, 0, [(0, 0)], W=2), 0)
        self.assertEqual(monitors.deadlocked_agents(rows, [(0, 0)], W=2), set())

    def test_safety_excludes_finished_robot_coordinates(self):
        rows = trace([[(0, 0), (0, 2)], [(0, 1), (0, 2)], [(0, 1), (0, 1)]])
        self.assertEqual(monitors.rho_safe(rows, [(0, 1), (0, 0)]), 1)
        self.assertEqual(monitors.rho_safe(rows, [(0, 9), (0, 0)]), -1)
        self.assertIsNone(monitors.rho_safe(trace([[(0, 0)]]), [(0, 1)]))

    def test_epistemic_rule_and_unattributed_labels(self):
        positions = [[(0, 0), (0, 1)]] * 3
        goals = [(0, 2), (0, 3)]
        claims = {0: {0: (0, 1), 1: (0, 1)}}
        for heard, label in (({0: [], 1: []}, "epistemic"),
                             ({0: [1], 1: [0]}, "rule_failure")):
            rows = trace(positions, heard)
            causes = monitors.deadlock_causes(rows, goals, W=2, intents=claims)
            self.assertEqual(causes, {0: label, 1: "unattributed"})
        self.assertEqual(monitors.deadlock_causes(trace(positions), goals, W=2),
                         {0: "unattributed", 1: "unattributed"})

    def test_invalid_trace_does_not_produce_plausible_scores(self):
        for rows in ([], [StepRecord(2, [(0, 0)], 0, 1, 0, {})],
                     [StepRecord(0, [], 0, 0, 0, {})]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                monitors.rho_reach(rows, 0, [(0, 1)])


class MetricsTests(unittest.TestCase):
    def record(self, recorder, t, positions, arrived=(), inboxes=None, degree=1):
        recorder.record(t, positions, {"mean_degree": degree, "n_components": 1},
                        list(arrived), inboxes or {})

    def test_snapshot_delivery_age_and_json_roundtrip(self):
        intentions = {0: (0, 1), 1: (0, 2)}
        recorder = Metrics([(0, 3), (0, 4)], seed=7, window=1,
                           intent_provider=lambda: intentions)
        positions = [[0, 0], [0, 1]]
        self.record(recorder, 0, positions)
        message = Message(0, (0, 0), (0, 3), sent_at=0, recipient=1)
        self.record(recorder, 1, positions, [message], {1: [message]})
        self.record(recorder, 2, positions, degree=99)  # terminal graph excluded
        positions[0][0] = 99
        intentions[0] = (99, 99)
        message.sender = 99
        self.assertEqual(recorder.trace[0].positions[0], (0, 0))
        self.assertEqual(recorder.trace[1].inbox_senders[1], [0])
        self.assertEqual(recorder.trace[1].max_age, 1)
        self.assertEqual(recorder.intents[0][0], (0, 1))
        restored = Metrics.from_data(json.loads(json.dumps(recorder.to_data())))
        self.assertEqual(restored.summary(), recorder.summary())
        self.assertEqual(restored.summary()["messages_per_agent_per_step"], 0.25)
        self.assertEqual(restored.summary()["mean_degree"], 1)

    def test_costs_use_first_arrivals(self):
        recorder = Metrics([(0, 1), (1, 3), (2, 4)], seed=1)
        for t in range(5):
            self.record(recorder, t, [(0, min(t, 1)), (1, min(t, 3)), (2, min(t, 4))])
        recorder.capture_environment([{"metrics": {"ISR": 1.0, "CSR": 1.0,
                                                  "SoC": 12, "makespan": 99}}])
        result = recorder.summary()
        self.assertEqual((result["SoC"], result["makespan"]), (8, 4))
        self.assertEqual(result["environment_metrics"]["SoC"], 12)
        self.assertEqual(result["cost_definition"], "first_arrival_steps_v1")
        recorder.capture_environment([{"metrics": {"ISR": 0.0, "CSR": 0.0, "SoC": 99, "makespan": 99}}])
        self.assertIsNone(recorder.summary()["SoC"])
        self.assertIsNone(recorder.summary()["makespan"])
        self.assertEqual(recorder.summary()["environment_metrics"]["SoC"], 99)

    def test_terminal_intentions_are_excluded(self):
        recorder = Metrics([(0, 4)], seed=1, intent_provider=lambda: {0: (0, 1)})
        self.record(recorder, 0, [(0, 0)])
        self.record(recorder, 1, [(0, 1)])
        self.assertEqual(recorder.intents, {0: {0: (0, 1)}})
        self.assertNotIn(1, recorder.to_data()["intents"])
        empty_run = Metrics([(0, 4)], seed=1, intent_provider=lambda: {0: (0, 1)})
        self.record(empty_run, 0, [(0, 0)])
        self.assertEqual(empty_run.to_data()["intents"], {})

    def test_legacy_bundle_recomputation(self):
        recorder = Metrics([(0, 1)], seed=1)
        self.record(recorder, 0, [(0, 0)])
        self.record(recorder, 1, [(0, 1)])
        recorder.capture_environment([{"metrics": {"ISR": 1.0, "CSR": 1.0,
                                                  "SoC": 99, "makespan": 99}}])
        data = recorder.to_data()
        data.pop("cost_definition")
        data["intents"][1] = {0: (0, 1)}  # Older bundles included a terminal cache.
        restored = Metrics.from_data(json.loads(json.dumps(data)))
        self.assertEqual(restored.summary()["SoC"], 1)
        self.assertEqual(restored.to_data()["cost_definition"], "first_arrival_steps_v1")
        self.assertNotIn(1, restored.intents)

    def test_success_requires_recorded_arrivals(self):
        recorder = Metrics([(0, 1)], seed=1)
        self.record(recorder, 0, [(0, 0)])
        recorder.capture_environment([{"metrics": {"ISR": 1.0, "CSR": 1.0}}])
        with self.assertRaisesRegex(ValueError, "missing an arrival"):
            recorder.summary()

    def test_zero_steps_and_missing_metrics_are_explicit_unknowns(self):
        recorder = Metrics([(0, 1)], seed=1)
        self.record(recorder, 0, [(0, 0)])
        result = recorder.summary()
        self.assertIsNone(result["ISR"])
        self.assertIsNone(result["rho_live_mean"])
        self.assertIsNone(result["pct_epistemic"])
        self.assertEqual(result["n_deadlocked"], 0)
        self.assertEqual(result["messages_per_agent_per_step"], 0)

    def test_invalid_records_and_empty_summary(self):
        recorder = Metrics([(0, 1)], seed=1)
        with self.assertRaises(ValueError):
            recorder.summary()
        with self.assertRaises(ValueError):
            self.record(recorder, 1, [(0, 0)])
        with self.assertRaises(ValueError):
            self.record(recorder, 0, [])
        with self.assertRaises(ValueError):
            self.record(recorder, 0, [(0, 0)], [Message(0, (0, 0), (0, 1), sent_at=1)])


if __name__ == "__main__":
    unittest.main()
