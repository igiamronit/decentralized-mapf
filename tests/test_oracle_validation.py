
import pytest

from decentralized_mapf.oracle.validation import (
    validate_problem,
    validate_paths,
)


def test_valid_paths():
    grid = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
    starts = [(0, 0), (2, 0)]
    goals = [(0, 2), (2, 2)]
    paths = [
        [(0, 0), (0, 1), (0, 2)],
        [(2, 0), (2, 1), (2, 2)],
    ]

    validate_paths(grid, starts, goals, paths)


def test_invalid_grid_shape():
    with pytest.raises(ValueError, match="rectangular"):
        validate_problem([[0, 0], [0]], [(0, 0)], [(0, 1)])


def test_invalid_grid_value():
    with pytest.raises(ValueError, match="Invalid grid value"):
        validate_problem([[0, 2]], [(0, 0)], [(0, 1)])


def test_start_in_obstacle():
    with pytest.raises(ValueError, match="obstacle"):
        validate_problem([[1, 0]], [(0, 0)], [(0, 1)])


def test_path_enters_obstacle():
    grid = [[0, 1, 0]]
    with pytest.raises(ValueError, match="obstacle"):
        validate_paths(
            grid,
            [(0, 0)],
            [(0, 2)],
            [[(0, 0), (0, 1), (0, 2)]],
        )


def test_illegal_move():
    grid = [[0, 0, 0], [0, 0, 0]]
    with pytest.raises(ValueError, match="illegal move"):
        validate_paths(
            grid,
            [(0, 0)],
            [(0, 2)],
            [[(0, 0), (1, 2), (0, 2)]],
        )




def test_vertex_collision():
    grid = [
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 0],
    ]

    starts = [(0, 0), (0, 2)]
    goals = [(2, 0), (2, 2)]

    paths = [
        [(0, 0), (0, 1), (1, 1), (2, 1), (2, 0)],
        [(0, 2), (0, 1), (0, 2), (1, 2), (2, 2)],
    ]

    with pytest.raises(ValueError, match="Vertex collision"):
        validate_paths(grid, starts, goals, paths)




def test_edge_collision():
    grid = [[0, 0]]
    with pytest.raises(ValueError, match="Edge collision"):
        validate_paths(
            grid,
            [(0, 0), (0, 1)],
            [(0, 1), (0, 0)],
            [
                [(0, 0), (0, 1)],
                [(0, 1), (0, 0)],
            ],
        )


def test_wrong_start():
    with pytest.raises(ValueError, match="starts at"):
        validate_paths(
            [[0, 0]],
            [(0, 0)],
            [(0, 1)],
            [[(0, 1)]],
        )


def test_wrong_goal():
    with pytest.raises(ValueError, match="ends at"):
        validate_paths(
            [[0, 0]],
            [(0, 0)],
            [(0, 1)],
            [[(0, 0)]],
        )


def test_duplicate_starts():
    with pytest.raises(ValueError, match="same start"):
        validate_problem(
            [[0, 0]],
            [(0, 0), (0, 0)],
            [(0, 1), (0, 1)],
        )
        

@pytest.mark.parametrize(
    "bad_position",
    [
        (1,),             # Only one coordinate
        (1, 1, 1),        # Three coordinates
        "11",             # String instead of a coordinate pair
        (0.5, 1),          # Float coordinate
        (True, 1),         # Boolean coordinate
    ],
)
def test_malformed_path_coordinates(bad_position):
    grid = [[0, 0], [0, 0]]

    with pytest.raises(ValueError):
        validate_paths(
            grid,
            [(0, 0)],
            [(1, 1)],
            [[(0, 0), bad_position, (1, 1)]],
        )

@pytest.mark.parametrize("bad_cell", [0.0, 1.0])
def test_float_grid_values_rejected(bad_cell):
    with pytest.raises(ValueError, match="Invalid grid value"):
        validate_problem(
            [[bad_cell, 0]],
            [(0, 1)],
            [(0, 1)],
        )
