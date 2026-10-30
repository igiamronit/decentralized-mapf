
from collections.abc import Sequence

Position = tuple[int, int]
Grid = Sequence[Sequence[int]]
Paths = Sequence[Sequence[Position]]


def _validate_position(position, label: str) -> Position:
    """Validate and normalize a (row, column) coordinate."""
    if not isinstance(position, (tuple, list)) or len(position) != 2:
        raise ValueError(f"{label} must be a (row, column) pair.")

    r, c = position

    # bool is a subclass of int in Python, so reject it explicitly.
    if (
        not isinstance(r, int)
        or isinstance(r, bool)
        or not isinstance(c, int)
        or isinstance(c, bool)
    ):
        raise ValueError(f"{label} coordinates must be integers.")

    return (r, c)


def validate_problem(
    grid_map: Grid,
    starts: Sequence[Position],
    goals: Sequence[Position],
) -> None:
    """Validate the grid and MAPF start/goal configuration.

    Grid convention:
        0 = free
        1 = obstacle

    Coordinates:
        (row, column)
    """
    if not isinstance(grid_map, Sequence) or isinstance(grid_map, (str, bytes)):
        raise ValueError("Grid must be a non-empty sequence of rows.")

    if not grid_map or not isinstance(grid_map[0], Sequence):
        raise ValueError("Grid must be non-empty.")

    if isinstance(grid_map[0], (str, bytes)) or not grid_map[0]:
        raise ValueError("Grid must be non-empty.")

    width = len(grid_map[0])

    for r, row in enumerate(grid_map):
        if (
            not isinstance(row, Sequence)
            or isinstance(row, (str, bytes))
            or len(row) != width
        ):
            raise ValueError("Grid must be rectangular.")

        for c, cell in enumerate(row):
                        if (
                not isinstance(cell, int)
                or isinstance(cell, bool)
                or cell not in (0, 1)
            ):
                            raise ValueError(
                    f"Invalid grid value {cell!r} at {(r, c)}; "
                    "expected 0 or 1."
                )

    if not isinstance(starts, Sequence) or not isinstance(goals, Sequence):
        raise ValueError("Starts and goals must be sequences.")

    if not starts:
        raise ValueError("At least one agent is required.")

    if len(starts) != len(goals):
        raise ValueError("Number of starts and goals must match.")

    height = len(grid_map)

    def check_cell(position, label: str) -> Position:
        r, c = _validate_position(position, label)

        if not (0 <= r < height and 0 <= c < width):
            raise ValueError(f"{label} {position} is outside the grid.")

        if grid_map[r][c] != 0:
            raise ValueError(f"{label} {position} is an obstacle.")

        return (r, c)

    normalized_starts = [
        check_cell(position, f"starts[{i}]")
        for i, position in enumerate(starts)
    ]

    normalized_goals = [
        check_cell(position, f"goals[{i}]")
        for i, position in enumerate(goals)
    ]

    if len(set(normalized_starts)) != len(normalized_starts):
        raise ValueError("Two agents cannot share the same start cell.")

    if len(set(normalized_goals)) != len(normalized_goals):
        raise ValueError("Two agents cannot share the same goal cell.")


def validate_paths(
    grid_map: Grid,
    starts: Sequence[Position],
    goals: Sequence[Position],
    paths: Paths,
) -> None:
    """Raise ValueError if the returned joint paths are not valid MAPF paths.

    Agents are assumed to remain at their final positions after reaching
    their goals when checking collisions across unequal path lengths.
    """
    validate_problem(grid_map, starts, goals)

    n_agents = len(starts)

    if (
        paths is None
        or not isinstance(paths, Sequence)
        or isinstance(paths, (str, bytes))
        or len(paths) != n_agents
    ):
        received = 0 if paths is None else (
            len(paths) if isinstance(paths, Sequence) else "invalid"
        )
        raise ValueError(
            f"Expected {n_agents} paths, received {received}."
        )

    normalized = []

    for i, path in enumerate(paths):
        if (
            not isinstance(path, Sequence)
            or isinstance(path, (str, bytes))
            or not path
        ):
            raise ValueError(f"Path {i} is empty or invalid.")

        normalized_path = [
            _validate_position(position, f"paths[{i}][{t}]")
            for t, position in enumerate(path)
        ]

        if normalized_path[0] != tuple(starts[i]):
            raise ValueError(
                f"Path {i} starts at {normalized_path[0]}, "
                f"expected {tuple(starts[i])}."
            )

        if normalized_path[-1] != tuple(goals[i]):
            raise ValueError(
                f"Path {i} ends at {normalized_path[-1]}, "
                f"expected {tuple(goals[i])}."
            )

        for t, (r, c) in enumerate(normalized_path):
            if not (
                0 <= r < len(grid_map)
                and 0 <= c < len(grid_map[0])
            ):
                raise ValueError(
                    f"Agent {i} leaves the grid at timestep {t}: {(r, c)}."
                )

            if grid_map[r][c] != 0:
                raise ValueError(
                    f"Agent {i} enters obstacle {(r, c)} at timestep {t}."
                )

        for t in range(1, len(normalized_path)):
            r0, c0 = normalized_path[t - 1]
            r1, c1 = normalized_path[t]

            distance = abs(r1 - r0) + abs(c1 - c0)

            if distance > 1:
                raise ValueError(
                    f"Agent {i} makes an illegal move "
                    f"from {normalized_path[t - 1]} to "
                    f"{normalized_path[t]} at timestep {t}."
                )

        normalized.append(normalized_path)

    horizon = max(len(path) for path in normalized)

    def position_at(agent: int, t: int) -> Position:
        path = normalized[agent]
        return path[min(t, len(path) - 1)]

    # Vertex collision checks.
    for t in range(horizon):
        occupied = {}

        for i in range(n_agents):
            position = position_at(i, t)

            if position in occupied:
                raise ValueError(
                    f"Vertex collision at timestep {t}, cell {position}, "
                    f"agents {occupied[position]} and {i}."
                )

            occupied[position] = i

    # Edge-swap collision checks.
    for t in range(horizon - 1):
        for i in range(n_agents):
            for j in range(i + 1, n_agents):
                i_now = position_at(i, t)
                i_next = position_at(i, t + 1)
                j_now = position_at(j, t)
                j_next = position_at(j, t + 1)

                if i_now == j_next and j_now == i_next:
                    raise ValueError(
                        f"Edge collision at timestep {t}->{t + 1} "
                        f"between agents {i} and {j}."
                    )
