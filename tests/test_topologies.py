
import unittest

from decentralized_mapf.communication import (
    GlobalCommunication,
    KNNCommunication,
    NoCommunication,
    RangeCommunication,
)


class TestRangeCommunication(unittest.TestCase):
    def test_range_edges(self):
        positions = [(0, 0), (0, 2), (0, 5), (3, 0)]
        model = RangeCommunication(2)

        self.assertEqual(
            model.get_edges(positions),
            {0: [1], 1: [0], 2: [], 3: []},
        )

    def test_range_zero_matches_no_communication(self):
        positions = [(0, 0), (0, 1), (2, 2)]
        self.assertEqual(
            RangeCommunication(0).get_edges(positions),
            NoCommunication().get_edges(positions),
        )

    def test_large_range_matches_global_communication(self):
        positions = [(0, 0), (0, 1), (2, 2)]
        self.assertEqual(
            RangeCommunication(float("inf")).get_edges(positions),
            GlobalCommunication().get_edges(positions),
        )

    def test_range_rejects_invalid_values(self):
        for value in (-1, None, "2", True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    RangeCommunication(value)

    def test_range_includes_all_robot_ids(self):
        edges = RangeCommunication(1).get_edges([])
        self.assertEqual(edges, {})


class TestKNNCommunication(unittest.TestCase):
    def test_knn_edges(self):
        positions = [(0, 0), (0, 1), (0, 3), (0, 10)]
        model = KNNCommunication(1)

        self.assertEqual(
            model.get_edges(positions),
            {0: [1], 1: [0], 2: [1], 3: [2]},
        )

    def test_knn_breaks_distance_ties_by_robot_id(self):
        positions = [(0, 0), (0, 2), (2, 0)]
        model = KNNCommunication(1)

        self.assertEqual(model.get_edges(positions)[0], [1])

    def test_knn_zero_has_no_edges(self):
        positions = [(0, 0), (0, 1), (2, 2)]
        edges = KNNCommunication(0).get_edges(positions)

        self.assertEqual(edges, {0: [], 1: [], 2: []})

    def test_knn_caps_neighbours_at_available_robots(self):
        positions = [(0, 0), (0, 1), (0, 2)]
        edges = KNNCommunication(10).get_edges(positions)

        self.assertEqual(
            {robot: len(neighbours) for robot, neighbours in edges.items()},
            {0: 2, 1: 2, 2: 2},
        )

    def test_knn_rejects_invalid_values(self):
        for value in (-1, 1.5, None, True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    KNNCommunication(value)

    def test_models_do_not_include_self_edges(self):
        positions = [(0, 0), (0, 1), (2, 2)]

        for model in (
            RangeCommunication(10),
            KNNCommunication(2),
        ):
            with self.subTest(model=type(model).__name__):
                edges = model.get_edges(positions)
                for robot, neighbours in edges.items():
                    self.assertNotIn(robot, neighbours)

    def test_models_return_every_robot_as_a_key(self):
        positions = [(0, 0), (0, 1), (2, 2)]
        expected_ids = {0, 1, 2}

        for model in (
            RangeCommunication(1),
            KNNCommunication(1),
        ):
            with self.subTest(model=type(model).__name__):
                self.assertEqual(
                    set(model.get_edges(positions)),
                    expected_ids,
                )


if __name__ == "__main__":
    unittest.main()
