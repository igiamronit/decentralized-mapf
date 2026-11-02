
from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
import time
import math

from pathlib import Path
from typing import Optional

from .validation import validate_problem, validate_paths

logger = logging.getLogger(__name__)

Position = tuple[int, int]
Paths = list[list[Position]]

_MAP_FREE = "."
_MAP_OBS = "@"

_RE_SOLVED = re.compile(r"^solved=(\d+)", re.MULTILINE)
_RE_SOLUTION_BLOCK = re.compile(
    r"^solution=\s*\n(.*)",
    re.DOTALL | re.MULTILINE,
)
_RE_TIMESTEP_LINE = re.compile(r"^(\d+):(.*)")
_RE_COORD_PAIR = re.compile(r"\((\d+),(\d+)\)")


class _OracleError(Exception):
    pass


class _OracleTimeoutError(_OracleError):
    pass


def _probe_binary() -> Optional[Path]:
    """Find the LaCAM3 executable lazily."""

    env_path = os.environ.get("LACAM3_BINARY_PATH")

    if env_path:
        candidate = Path(env_path).expanduser()
        if candidate.is_file():
            return candidate.resolve()

        logger.warning(
            "LACAM3_BINARY_PATH does not exist: %s", candidate
        )

    # This file is:
    # repo/decentralized_mapf/oracle/lacam_adapter.py
    project_root = Path(__file__).resolve().parents[2]

    candidates = [
        project_root / "lacam3_src" / "build" / "main.exe",
        project_root / "lacam3_src" / "build" / "main",
        project_root / "lacam3" / "build" / "main.exe",
        project_root / "lacam3" / "build" / "main",
    ]

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    return None


def _write_map_file(grid_map: list[list[int]], path: Path) -> None:
    """Write a Moving AI .map file. 0=free, 1=obstacle."""

    height = len(grid_map)
    width = len(grid_map[0])

    lines = [
        "type octile",
        f"height {height}",
        f"width {width}",
        "map",
    ]

    for row in grid_map:
        lines.append(
            "".join(
                _MAP_OBS if cell == 1 else _MAP_FREE
                for cell in row
            )
        )

    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def _write_scen_file(
    map_path: Path,
    starts: list[Position],
    goals: list[Position],
    grid_map: list[list[int]],
    scen_path: Path,
) -> None:
    """Write Moving AI scenario data.

    Python uses (row, column).
    LaCAM3 uses (x, y) = (column, row).
    """

    height = len(grid_map)
    width = len(grid_map[0])

    lines = ["version 1"]

    for i, (start, goal) in enumerate(zip(starts, goals)):
        sr, sc = start
        gr, gc = goal

        lines.append(
            f"{i}\t{map_path}\t{width}\t{height}\t"
            f"{sc}\t{sr}\t{gc}\t{gr}\t0"
        )

    scen_path.write_text("\n".join(lines) + "\n", encoding="ascii")



def _parse_result(result_text: str, n_agents: int) -> Paths:
    """Convert (x,y) to (row,col), preserving every solver timestep.

    Keep goal revisits and terminal waits for full-trajectory validation.
    First-arrival cost calculation belongs to oracle.metrics, not parsing.
    """

    if not isinstance(result_text, str):
        raise _OracleError("LaCAM3 result must be text.")

    if (
        not isinstance(n_agents, int)
        or isinstance(n_agents, bool)
        or n_agents <= 0
    ):
        raise _OracleError("Expected a positive integer agent count.")

    solved = _RE_SOLVED.search(result_text)

    if not solved or solved.group(1) != "1":
        raise _OracleError("LaCAM3 did not report solved=1.")

    solution = _RE_SOLUTION_BLOCK.search(result_text)

    if not solution:
        raise _OracleError("LaCAM3 result has no solution block.")

    positions_by_t: dict[int, list[Position]] = {}

    for line_number, raw_line in enumerate(
        solution.group(1).splitlines(), start=1
    ):
        line = raw_line.strip()

        if not line:
            continue

        timestep = _RE_TIMESTEP_LINE.fullmatch(line)

        if not timestep:
            raise _OracleError(
                f"Malformed solution line {line_number}: {line!r}."
            )

        t = int(timestep.group(1))

        if t in positions_by_t:
            raise _OracleError(f"Duplicate timestep {t} in LaCAM3 output.")

        coordinate_text = timestep.group(2).strip()
        matches = list(_RE_COORD_PAIR.finditer(coordinate_text))

        if not matches:
            raise _OracleError(
                f"Malformed coordinates at timestep {t}: "
                f"{coordinate_text!r}."
            )

        coordinates = [match.groups() for match in matches]
        cursor = 0

        for match in matches:
            separator = coordinate_text[cursor:match.start()]

            if cursor == 0:
                if separator.strip():
                    raise _OracleError(
                        f"Malformed coordinates at timestep {t}."
                    )
            elif separator.strip() != ",":
                raise _OracleError(
                    f"Malformed coordinate separator at timestep {t}."
                )

            cursor = match.end()

        trailing = coordinate_text[cursor:].strip()

        if trailing not in ("", ","):
            raise _OracleError(
                f"Malformed trailing content at timestep {t}."
            )

        if len(coordinates) != n_agents:
            raise _OracleError(
                f"At timestep {t}, expected {n_agents} positions; "
                f"received {len(coordinates)}."
            )

        # LaCAM3 (x=column, y=row) -> Python (row, column)
        positions_by_t[t] = [
            (int(y), int(x)) for x, y in coordinates
        ]

    if not positions_by_t:
        raise _OracleError("No valid timestep lines in solution.")

    # Allocate by the number of output rows, never by an untrusted timestamp.
    # A sparse huge timestamp previously tried to materialize range(max_t+1).
    timesteps = sorted(positions_by_t)
    if any(t != expected for expected, t in enumerate(timesteps)):
        raise _OracleError("LaCAM3 output has missing timesteps.")

    paths: Paths = [[] for _ in range(n_agents)]

    for t in timesteps:
        for agent_id, position in enumerate(positions_by_t[t]):
            paths[agent_id].append(position)

    return paths


def _solve_via_binary(
    binary: Path,
    grid_map: list[list[int]],
    starts: list[Position],
    goals: list[Position],
    timeout: float,
) -> Paths:
    """Run LaCAM3 and parse its output."""

    with tempfile.TemporaryDirectory(
        prefix="oracle_lacam3_"
    ) as tmpdir:

        tmp = Path(tmpdir)
        map_path = tmp / "grid.map"
        scen_path = tmp / "agents.scen"
        result_path = tmp / "result.txt"

        _write_map_file(grid_map, map_path)

        _write_scen_file(
            map_path, starts, goals, grid_map, scen_path
        )

        command = [
            str(binary),
            "--map", str(map_path),
            "--scen", str(scen_path),
            "--num", str(len(starts)),
            "--time_limit_sec", str(max(1, int(timeout))),
            "--verbose", "0",
            "--output", str(result_path),
        ]

        logger.info("Running LaCAM3: %s", command)

        try:
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout + 5,
                cwd=str(binary.parent),
            )
        except subprocess.TimeoutExpired as exc:
            raise _OracleTimeoutError(
                "LaCAM3 exceeded its wall-clock timeout."
            ) from exc

        if process.returncode != 0:
            raise _OracleError(
                f"LaCAM3 exited with code {process.returncode}. "
                f"stderr: {process.stderr[:500]}"
            )

        if not result_path.is_file():
            raise _OracleError("LaCAM3 did not create result.txt.")

        result_text = result_path.read_text(
            encoding="utf-8",
            errors="replace",
        )

        return _parse_result(result_text, len(starts))



def oracle_solve(
    grid_map: list[list[int]],
    starts: list[Position],
    goals: list[Position],
    timeout: float = 30,
) -> Optional[Paths]:
    """Solve a MAPF instance using centralized LaCAM3.

    Returns:
        List of paths, preserving agent ordering, on success.
        None on invalid input, timeout, missing binary, or solver failure.

    Paths preserve the complete solver timeline, including goal revisits and
    terminal waits. Validate that timeline before reporting first-arrival costs
    with oracle_metrics(); do not truncate paths at their first goal visit.
    """

    try:
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("timeout must be a finite positive number.")
        validate_problem(grid_map, starts, goals)

        binary = _probe_binary()

        if binary is None:
            raise _OracleError(
                "LaCAM3 binary not found. Set LACAM3_BINARY_PATH."
            )

        start_time = time.monotonic()

        paths = _solve_via_binary(
            binary,
            grid_map,
            starts,
            goals,
            timeout,
        )

        elapsed = time.monotonic() - start_time

        if elapsed > timeout + 5:
            raise _OracleTimeoutError("Oracle exceeded timeout.")

        validate_paths(grid_map, starts, goals, paths)

        logger.info(
            "LaCAM3 solved %d agents in %.2f seconds.",
            len(starts),
            elapsed,
        )

        return paths

    except _OracleTimeoutError as exc:
        logger.warning("LaCAM3 timeout: %s", exc)

    except Exception as exc:
        logger.warning(
            "Oracle solve failed (%s): %s",
            type(exc).__name__,
            exc,
        )

    return None



