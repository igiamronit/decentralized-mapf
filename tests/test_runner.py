"""Integration checks with real POGEMA and small test-only collaborators."""

import unittest

from pogema import GridConfig, pogema_v0

from decentralized_mapf import (
    Channel, GlobalCommunication, KNNCommunication, Message, NoCommunication,
    PerfectChannel, Planner, RangeCommunication, StepRecord, run_episode,
)
from decentralized_mapf.runner import _active_edges


class RecordingMetrics:
    def __init__(self):
        self.trace = []

    def record(self, t, positions, graph_stats, arrived, inboxes):
        self.trace.append(StepRecord(
            t, list(positions), graph_stats["mean_degree"], graph_stats["n_components"],
            len(arrived), {i: [m.sender for m in inbox] for i, inbox in inboxes.items()},
            max((t - m.sent_at for m in arrived), default=0),
        ))

    def summary(self):
        return {"steps": len(self.trace) - 1,
                "messages": sum(row.n_messages for row in self.trace)}


class ScriptedPlanner(Planner):
    def __init__(self, actions=None):
        self.actions = actions or {}
        self.resets = 0

    def reset(self):
        self.resets += 1
        self.state = {}
        self.events = []
        self.heard = []
        self.payloads = []

    def observe(self, agent_id, observation, position, goal):
        self.state[agent_id] = (position, goal)
        self.events.append(("observe", agent_id, position, tuple(observation["xy"])))

    def compose(self, agent_id, t):
        position, goal = self.state[agent_id]
        self.events.append(("compose", agent_id))
        message = Message(agent_id, position, goal, [position], sent_at=t)
        self.payloads.append(message)
        return message

    def act(self, agent_id, observation, inbox, goal):
        self.heard.append((agent_id, inbox))
        return self.actions.get(agent_id, 0)


class DropOneChannel(Channel):
    def deliver(self, messages, t):
        self.sent = messages
        return [m for m in messages if (m.sender, m.recipient) != (0, 1)]


class OneStepDelay(Channel):
    def __init__(self):
        self.queue = []
        self.resets = 0

    def reset(self):
        self.resets += 1
        self.queue.clear()

    def deliver(self, messages, t):
        self.queue.extend((t + 1, m) for m in messages)
        due = [m for arrival, m in self.queue if arrival <= t]
        self.queue = [(arrival, m) for arrival, m in self.queue if arrival > t]
        return due


class SwitchingTopology(GlobalCommunication):
    def __init__(self):
        self.calls = 0

    def get_edges(self, positions):
        receiver = 1 if self.calls == 0 else 2
        self.calls += 1
        return {0: [receiver], 1: [], 2: []}


class RunnerTests(unittest.TestCase):
    def environment(self, **overrides):
        settings = dict(
            map=".........\n.........", num_agents=3,
            agents_xy=[[0, 0], [0, 4], [0, 8]],
            targets_xy=[[1, 0], [1, 4], [1, 8]],
            obs_radius=2, seed=7, max_episode_steps=10,
            observation_type="POMAPF", on_target="finish",
            collision_system="priority", integration=None,
        )
        settings.update(overrides)
        env = pogema_v0(grid_config=GridConfig(**settings))
        self.addCleanup(env.close)
        return env

    def test_global_and_none_with_same_seed_and_complete_trace(self):
        traces = []
        for comm, count in ((GlobalCommunication(), 12), (NoCommunication(), 0)):
            metrics = RecordingMetrics()
            planner = ScriptedPlanner()
            result = run_episode(self.environment(), comm, PerfectChannel(), planner, metrics, 2)
            self.assertEqual(result, {"steps": 2, "messages": count})
            self.assertEqual([row.t for row in metrics.trace], [0, 1, 2])
            self.assertEqual(metrics.trace[-1].n_messages, 0)
            self.assertEqual(metrics.trace[0].positions, [(0, 0), (0, 4), (0, 8)])
            self.assertEqual([event[0] for event in planner.events[:6]],
                             ["observe"] * 3 + ["compose"] * 3)
            traces.append([row.positions for row in metrics.trace])
        self.assertEqual(*traces)

    def test_independent_transmissions_and_single_edge_drop(self):
        metrics, planner, channel = RecordingMetrics(), ScriptedPlanner(), DropOneChannel()
        run_episode(self.environment(), GlobalCommunication(), channel, planner, metrics, 1)
        self.assertEqual(metrics.trace[0].n_messages, 5)
        self.assertEqual(metrics.trace[0].inbox_senders, {0: [1, 2], 1: [2], 2: [0, 1]})
        first, second = channel.sent[:2]
        self.assertIsNot(first, second)
        first.next_cells.append((99, 99))
        self.assertEqual(second.next_cells, [(0, 0)])
        self.assertEqual(planner.payloads[0].next_cells, [(0, 0)])
        self.assertIsNone(planner.payloads[0].recipient)

    def test_delay_keeps_original_recipient_when_graph_changes(self):
        metrics, planner = RecordingMetrics(), ScriptedPlanner()
        run_episode(self.environment(), SwitchingTopology(), OneStepDelay(), planner, metrics, 2)
        self.assertEqual(metrics.trace[0].n_messages, 0)
        self.assertEqual(metrics.trace[1].inbox_senders, {0: [], 1: [0], 2: []})
        self.assertEqual(metrics.trace[1].max_age, 1)
        delivered = [inbox[0] for agent_id, inbox in planner.heard if agent_id == 1 and inbox]
        self.assertEqual((delivered[0].position, delivered[0].sent_at), ((0, 0), 0))

    def test_arrivals_refresh_observations_and_remove_finished_robots(self):
        env = self.environment(num_agents=2, agents_xy=[[0, 0], [0, 8]],
                               targets_xy=[[0, 1], [0, 6]])
        moves = [tuple(move) for move in env.unwrapped.grid_config.MOVES]
        planner = ScriptedPlanner({0: moves.index((0, 1)), 1: moves.index((0, -1))})
        metrics = RecordingMetrics()
        result = run_episode(env, GlobalCommunication(), PerfectChannel(), planner, metrics, 10)
        self.assertEqual(result, {"steps": 2, "messages": 2})
        self.assertEqual(metrics.trace[-1].positions, [(0, 1), (0, 6)])
        self.assertEqual([row.mean_degree for row in metrics.trace], [1.0, 0.0, 0.0])
        self.assertEqual([row.n_components for row in metrics.trace], [1, 1, 0])
        observations = [event for event in planner.events if event[0] == "observe"]
        self.assertEqual(observations[-1], ("observe", 1, (0, 7), (0, -1)))
        self.assertEqual([i for i, _ in planner.heard], [0, 1, 1])

    def test_delayed_messages_to_finished_robots_are_not_delivered(self):
        env = self.environment(targets_xy=[[0, 1], [1, 4], [1, 8]])
        moves = [tuple(move) for move in env.unwrapped.grid_config.MOVES]
        metrics = RecordingMetrics()
        run_episode(env, GlobalCommunication(), OneStepDelay(),
                    ScriptedPlanner({0: moves.index((0, 1))}), metrics, 2)
        self.assertEqual(metrics.trace[1].inbox_senders, {0: [], 1: [0, 2], 2: [0, 1]})
        self.assertEqual(metrics.trace[1].n_messages, 4)
        self.assertEqual(metrics.trace[1].mean_degree, 1.0)

    def test_knn_reselects_neighbours_after_middle_robot_finishes(self):
        env = self.environment()
        moves = [tuple(move) for move in env.unwrapped.grid_config.MOVES]
        planner, metrics = ScriptedPlanner({1: moves.index((1, 0))}), RecordingMetrics()
        result = run_episode(env, KNNCommunication(1), PerfectChannel(), planner, metrics, 2)
        self.assertEqual(result, {"steps": 2, "messages": 5})
        self.assertEqual(metrics.trace[1].inbox_senders, {0: [2], 1: [], 2: [0]})
        self.assertEqual(metrics.trace[1].mean_degree, 1.0)
        self.assertEqual(metrics.trace[1].n_components, 1)
        self.assertEqual([i for i, _ in planner.heard], [0, 1, 2, 0, 2])

    def test_active_selection_keeps_original_ids_for_all_topologies(self):
        positions, active = [(0, 0), (0, 1), (0, 2)], [True, False, True]
        connected, isolated = {0: [2], 2: [0]}, {0: [], 2: []}
        for model, expected in ((GlobalCommunication(), connected), (NoCommunication(), isolated),
                                (RangeCommunication(1), isolated), (RangeCommunication(2), connected),
                                (KNNCommunication(1), connected)):
            with self.subTest(model=type(model).__name__, expected=expected):
                self.assertEqual(_active_edges(model, positions, active), expected)

    def test_knn_ties_keep_original_robot_id_order(self):
        positions = [(99, 99), (0, 0), (99, 98), (0, 2), (2, 0)]
        self.assertEqual(
            _active_edges(KNNCommunication(1), positions, [False, True, False, True, True]),
            {1: [3], 3: [1], 4: [1]},
        )

    def test_empty_and_single_active_graphs(self):
        positions = [(0, 0), (0, 1), (0, 2)]
        for model in (GlobalCommunication(), NoCommunication(), RangeCommunication(3),
                      KNNCommunication(10)):
            with self.subTest(model=type(model).__name__):
                self.assertEqual(_active_edges(model, positions, [False, False, False]), {})
                self.assertEqual(_active_edges(model, positions, [False, False, True]), {2: []})

    def test_reset_clears_channel_and_planner_between_episodes(self):
        env, planner, channel = self.environment(), ScriptedPlanner(), OneStepDelay()
        for _ in range(2):
            metrics = RecordingMetrics()
            self.assertEqual(run_episode(env, GlobalCommunication(), channel, planner, metrics, 1),
                             {"steps": 1, "messages": 0})
        self.assertEqual(channel.resets, 2)
        self.assertEqual(planner.resets, 2)
        self.assertEqual(len(planner.heard), 3)

    def test_environment_timeout_and_zero_step_limit(self):
        for limit, env_limit, expected in ((10, 1, 1), (0, 10, 0)):
            metrics, planner = RecordingMetrics(), ScriptedPlanner()
            result = run_episode(self.environment(max_episode_steps=env_limit),
                                 NoCommunication(), PerfectChannel(), planner, metrics, limit)
            self.assertEqual(result["steps"], expected)
            self.assertEqual(len(metrics.trace), expected + 1)

    def test_blocked_moves_broadcast_actual_positions(self):
        env = self.environment(num_agents=2, agents_xy=[[0, 0], [0, 1]],
                               targets_xy=[[0, 8], [1, 0]])
        moves = [tuple(move) for move in env.unwrapped.grid_config.MOVES]
        planner = ScriptedPlanner({0: moves.index((0, 1)), 1: moves.index((0, -1))})
        metrics = RecordingMetrics()
        run_episode(env, GlobalCommunication(), PerfectChannel(), planner, metrics, 2)
        self.assertTrue(all(row.positions == [(0, 0), (0, 1)] for row in metrics.trace))
        self.assertEqual([m.position for m in planner.payloads],
                         [(0, 0), (0, 1), (0, 0), (0, 1)])

    def test_original_planner_methods_work_with_default_hooks(self):
        class MinimalPlanner(Planner):
            def compose(self, agent_id, t):
                return Message(agent_id, (0, 0), (1, 0), sent_at=t)

            def act(self, agent_id, observation, inbox, goal):
                return 0

        result = run_episode(self.environment(), NoCommunication(), PerfectChannel(),
                             MinimalPlanner(), RecordingMetrics(), 1)
        self.assertEqual(result, {"steps": 1, "messages": 0})

    def test_channel_must_preserve_recipient(self):
        class BadChannel(Channel):
            def deliver(self, messages, t):
                messages[0].recipient = None
                return messages

        with self.assertRaisesRegex(ValueError, "valid recipient"):
            run_episode(self.environment(), GlobalCommunication(), BadChannel(),
                        ScriptedPlanner(), RecordingMetrics(), 1)

    def test_invalid_run_settings(self):
        for settings, limit in (({}, -1), ({"on_target": "restart"}, 1),
                                ({"observation_type": "MAPF"}, 1), ({"seed": None}, 1)):
            with self.subTest(settings=settings, limit=limit), self.assertRaises(ValueError):
                run_episode(self.environment(**settings), NoCommunication(), PerfectChannel(),
                            ScriptedPlanner(), RecordingMetrics(), limit)


if __name__ == "__main__":
    unittest.main()
