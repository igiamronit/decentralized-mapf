"""Check communication semantics and shared graph statistics without POGEMA."""

from itertools import product
import unittest

from decentralized_mapf import CommunicationModel, GlobalCommunication, NoCommunication
from decentralized_mapf.communication import graph_stats


class CommunicationTests(unittest.TestCase):
    def test_three_robot_links(self):
        positions = [(0, 0), (0, 1), (50, 50)]
        self.assertEqual(
            GlobalCommunication().get_edges(positions),
            {0: [1, 2], 1: [0, 2], 2: [0, 1]},
        )
        self.assertEqual(NoCommunication().get_edges(positions), {0: [], 1: [], 2: []})

    def test_model_statistics_at_different_sizes(self):
        for n_agents in (0, 1, 2, 10, 100):
            positions = [(i, 0) for i in range(n_agents)]
            for model in (GlobalCommunication(), NoCommunication()):
                with self.subTest(n_agents=n_agents, model=type(model).__name__):
                    self.assertIsInstance(model, CommunicationModel)
                    edges = model.get_edges(positions)
                    global_mode = isinstance(model, GlobalCommunication)
                    self.assertEqual(sum(map(len, edges.values())),
                                     n_agents * (n_agents - 1) if global_mode else 0)
                    self.assertEqual(model.graph_stats(edges), {
                        "mean_degree": float(max(0, n_agents - 1)) if global_mode else 0.0,
                        "n_components": int(n_agents > 0) if global_mode else n_agents,
                        "is_connected": n_agents > 0 if global_mode else n_agents == 1,
                    })

    def test_models_are_deterministic_and_return_independent_lists(self):
        positions = [(0, 0), (0, 0), (99, -10)]
        for model in (GlobalCommunication(), NoCommunication()):
            with self.subTest(model=type(model).__name__):
                first = model.get_edges(positions)
                self.assertEqual(first, model.get_edges([(20, 40)] * 3))
                first[0].append(999)
                self.assertNotIn(999, first[1])
                self.assertNotIn(999, model.get_edges(positions)[0])
        self.assertEqual(positions, [(0, 0), (0, 0), (99, -10)])

    def test_directed_links_use_weak_connectivity_and_outgoing_degree(self):
        edges = {0: [1], 1: [], 2: [1], 3: []}
        self.assertEqual(graph_stats(edges), {
            "mean_degree": 0.5, "n_components": 2, "is_connected": False,
        })
        self.assertEqual(edges, {0: [1], 1: [], 2: [1], 3: []})
        self.assertEqual(graph_stats({0: [], 1: [0], 2: [1]}), {
            "mean_degree": 2 / 3, "n_components": 1, "is_connected": True,
        })

    def test_nonconsecutive_robot_ids(self):
        self.assertEqual(graph_stats({5: [9], 9: [], 20: []}), {
            "mean_degree": 1 / 3, "n_components": 2, "is_connected": False,
        })

    def test_missing_receiver_key_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Receiver 1"):
            graph_stats({0: [1]})

    def test_all_four_robot_directed_graphs_against_reachability(self):
        # Independent reference: transitive closure of the undirected adjacency
        # matrix, covering all 4,096 simple directed graphs on four robots.
        pairs = [(i, j) for i in range(4) for j in range(4) if i != j]
        for present in product((False, True), repeat=len(pairs)):
            edges = {i: [] for i in range(4)}
            reach = [[i == j for j in range(4)] for i in range(4)]
            for (i, j), enabled in zip(pairs, present):
                if enabled:
                    edges[i].append(j)
                    reach[i][j] = reach[j][i] = True
            for k in range(4):
                for i in range(4):
                    for j in range(4):
                        reach[i][j] = reach[i][j] or (reach[i][k] and reach[k][j])
            components = len({tuple(row) for row in reach})
            self.assertEqual(graph_stats(edges), {
                "mean_degree": sum(present) / 4,
                "n_components": components,
                "is_connected": components == 1,
            }, msg=str(edges))


if __name__ == "__main__":
    unittest.main()
