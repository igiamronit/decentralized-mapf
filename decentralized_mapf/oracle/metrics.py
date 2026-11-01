"""Project first-arrival costs over complete, validated oracle trajectories.

The final cell is each path's fixed goal. Costs follow the decentralized
first_arrival_steps_v1 convention; they are not LaCAM3's native stay-at-goal
objective when a robot visits its goal and later moves away.
"""

from collections.abc import Sequence
from typing import Optional
import math

Position = tuple[int, int]
Paths = list[list[Position]]

# Count transitions until first arrival, matching POGEMA finish-mode reporting.
PATH_CONVENTION = "transitions"


def _validate_paths(paths: Paths) -> None:
    if not isinstance(paths, list):
        raise TypeError("paths must be a list of agent paths.")

    if not paths:
        raise ValueError("paths must contain at least one agent.")

    for i, path in enumerate(paths):
        if not isinstance(path, (list, tuple)) or not path:
            raise ValueError(f"paths[{i}] is empty or invalid.")


def _cost(path: Sequence[Position], convention: str) -> int:
    """Infer the fixed goal from the endpoint without altering the trajectory."""
    goal = tuple(path[-1])
    arrival = next(t for t, cell in enumerate(path) if tuple(cell) == goal)
    if convention == "transitions":
        return arrival
    if convention == "positions":
        return arrival + 1

    raise ValueError(
        f"Unknown path convention {convention!r}. "
        "Expected 'transitions' or 'positions'."
    )


def makespan(
    paths: Paths,
    convention: Optional[str] = None,
) -> int:
    _validate_paths(paths)
    conv = convention or PATH_CONVENTION
    return max(_cost(path, conv) for path in paths)


def sum_of_costs(
    paths: Paths,
    convention: Optional[str] = None,
) -> int:
    _validate_paths(paths)
    conv = convention or PATH_CONVENTION
    return sum(_cost(path, conv) for path in paths)


def oracle_metrics(
    paths: Paths | None,
    convention: Optional[str] = None,
) -> dict[str, int]:
    """Report first-arrival makespan and SoC without removing path evidence.

    Frozen C6 interface:
        oracle_metrics(paths) -> {'makespan': int, 'SoC': int}

    Each path must end at its fixed goal, as checked by validate_paths in the
    adapter. The default counts transitions up to the first goal visit, even
    when the complete trajectory contains later waits or goal departures.
    The legacy 'positions' convention also counts the initial sample.
    """
    if paths is None:
        raise ValueError(
            "Oracle returned None. Cannot calculate metrics."
        )

    return {
        "makespan": makespan(paths, convention),
        "SoC": sum_of_costs(paths, convention),
    }


def oracle_soc_ratio(
    decentralized_soc: int | float,
    oracle_soc: int | float,
) -> float:
    for name, value in (
        ("decentralized_soc", decentralized_soc),
        ("oracle_soc", oracle_soc),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValueError(
                f"{name} must be a finite non-negative number."
            )

    if oracle_soc == 0:
        raise ValueError("Oracle SoC is zero; ratio is undefined.")

    return decentralized_soc / oracle_soc
