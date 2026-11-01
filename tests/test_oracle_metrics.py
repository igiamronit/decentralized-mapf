
import pytest
from copy import deepcopy

from decentralized_mapf.oracle.metrics import (
    oracle_metrics,
    oracle_soc_ratio,
    makespan,
    sum_of_costs,
    PATH_CONVENTION,
)


def test_path_convention():
    assert PATH_CONVENTION == "transitions"


def test_oracle_metrics_basic():
    paths = [
        [(0, 0), (0, 1), (0, 2)],
        [(2, 0), (1, 0)],
    ]

    result = oracle_metrics(paths)

    assert result == {"makespan": 2, "SoC": 3}


def test_agent_already_at_goal():
    paths = [
        [(0, 0)],
        [(2, 0), (1, 0), (0, 0)],
    ]

    assert oracle_metrics(paths) == {
        "makespan": 2,
        "SoC": 2,
    }


def test_all_agents_already_at_goal():
    paths = [[(0, 0)], [(1, 1)]]

    assert oracle_metrics(paths) == {
        "makespan": 0,
        "SoC": 0,
    }


@pytest.mark.parametrize("convention,offset", [("transitions", 0), ("positions", 1)])
@pytest.mark.parametrize("paths,arrivals", [
    ([[(0, 0), (0, 1), (0, 1), (0, 1), (0, 1)],
      [(1, 0), (1, 1), (1, 2), (1, 3), (1, 4)]], [1, 4]),
    ([[(0, 0)] * 5,
      [(1, 0), (1, 1), (1, 2), (1, 3), (1, 4)]], [0, 4]),
    ([[(0, 0), (0, 1), (1, 1), (1, 1), (0, 1)],
      [(2, 0), (2, 1), (2, 2), (2, 2), (2, 2)]], [1, 2]),
    ([[(0, 0), (0, 0), (0, 0), (0, 1)],
      [(1, 0), (1, 1), (1, 1), (1, 1)]], [3, 1]),
])
def test_full_timelines_use_first_arrivals_without_modifying_paths(paths, arrivals, convention, offset):
    original = deepcopy(paths)
    assert oracle_metrics(paths, convention) == {
        "makespan": max(arrivals) + offset,
        "SoC": sum(arrivals) + len(arrivals) * offset,
    }
    assert paths == original


def test_positions_convention():
    paths = [[(0, 0), (0, 1)], [(1, 0)]]

    assert oracle_metrics(paths, "positions") == {
        "makespan": 2,
        "SoC": 3,
    }


def test_standalone_metrics():
    paths = [
        [(0, 0), (0, 1), (0, 2)],
        [(2, 0), (1, 0)],
    ]

    assert makespan(paths) == 2
    assert sum_of_costs(paths) == 3


def test_empty_paths():
    with pytest.raises(ValueError):
        oracle_metrics([])


def test_empty_individual_path():
    with pytest.raises(ValueError):
        oracle_metrics([[]])


def test_none_paths():
    with pytest.raises(ValueError):
        oracle_metrics(None)


def test_unknown_convention():
    with pytest.raises(ValueError):
        oracle_metrics([[(0, 0)]], "invalid")


def test_soc_ratio():
    assert oracle_soc_ratio(120, 100) == pytest.approx(1.2)


def test_soc_ratio_zero_oracle():
    with pytest.raises(ValueError):
        oracle_soc_ratio(10, 0)

@pytest.mark.parametrize(
    "invalid_soc",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        True,
        "100",
        -1,
    ],
)
def test_invalid_decentralized_soc_rejected(invalid_soc):
    with pytest.raises(ValueError):
        oracle_soc_ratio(invalid_soc, 100)


@pytest.mark.parametrize(
    "invalid_soc",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        True,
        "100",
        -1,
    ],
)
def test_invalid_oracle_soc_rejected(invalid_soc):
    with pytest.raises(ValueError):
        oracle_soc_ratio(100, invalid_soc)
