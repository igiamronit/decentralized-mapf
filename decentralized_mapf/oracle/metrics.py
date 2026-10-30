
from collections.abc import Sequence
from typing import Optional
import math

Position = tuple[int, int]
Paths = list[list[Position]]

# LaCAM3 and POGEMA use transition-based costs.
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
    if convention == "transitions":
        return len(path) - 1
    if convention == "positions":
        return len(path)

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
    """
    Frozen C6 interface:
        oracle_metrics(paths) -> {'makespan': int, 'SoC': int}
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
