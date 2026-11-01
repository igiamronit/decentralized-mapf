
from pathlib import Path
from decentralized_mapf.oracle.metrics import oracle_metrics
import pytest
import decentralized_mapf.oracle.lacam_adapter as adapter

from decentralized_mapf.oracle.lacam_adapter import (
    oracle_solve,
    _parse_result,
    _write_map_file,
    _write_scen_file,
)


def test_import_and_unavailable_binary(monkeypatch):
    monkeypatch.setattr(
        "decentralized_mapf.oracle.lacam_adapter._probe_binary",
        lambda: None,
    )

    result = oracle_solve(
        [[0, 0]],
        [(0, 0)],
        [(0, 1)],
    )

    assert result is None


def test_mismatched_input_returns_none():
    assert oracle_solve(
        [[0, 0]],
        [(0, 0)],
        [],
    ) is None


def test_invalid_grid_returns_none():
    assert oracle_solve(
        [[0, 2]],
        [(0, 0)],
        [(0, 1)],
    ) is None


def test_parse_result_coordinate_conversion():
    result = """solved=1
makespan=2
solution=
0:(0,0),(2,0),
1:(1,0),(1,1),
2:(2,0),(0,2),
"""

    paths = _parse_result(result, 2)

    assert paths == [
        [(0, 0), (0, 1), (0, 2)],
        [(0, 2), (1, 1), (2, 0)],
    ]


def test_parse_unsolved_result():
    with pytest.raises(Exception):
        _parse_result("solved=0\n", 1)


def test_map_file_format(tmp_path):
    grid = [
        [0, 1],
        [1, 0],
    ]

    path = tmp_path / "test.map"

    _write_map_file(grid, path)

    content = path.read_text()

    assert "height 2" in content
    assert "width 2" in content
    assert ".@" in content
    assert "@." in content


def test_scen_file_coordinate_conversion(tmp_path):
    grid = [[0, 0], [0, 0]]

    map_path = tmp_path / "test.map"
    scen_path = tmp_path / "test.scen"

    _write_map_file(grid, map_path)

    _write_scen_file(
        map_path,
        [(1, 0)],
        [(0, 1)],
        grid,
        scen_path,
    )

    content = scen_path.read_text()

    # Start (row=1, col=0) becomes (x=0, y=1).
    # Goal (row=0, col=1) becomes (x=1, y=0).
    assert "\t0\t1\t1\t0\t0" in content
def test_subprocess_timeout_returns_none(monkeypatch):
    import subprocess
    import decentralized_mapf.oracle.lacam_adapter as adapter

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=args[0],
            timeout=kwargs.get("timeout", 1),
        )

    monkeypatch.setattr(adapter.subprocess, "run", fake_run)

    grid = [[0, 0], [0, 0]]
    starts = [(0, 0)]
    goals = [(1, 1)]

    result = adapter.oracle_solve(
        grid, starts, goals, timeout=1
    )

    assert result is None
    
@pytest.mark.parametrize(
    "timeout",
    [
        0,
        -1,
        float("nan"),
        float("inf"),
        float("-inf"),
        True,
    ],
)
def test_invalid_timeout_returns_none(timeout):
    result = oracle_solve(
        [[0, 0]],
        [(0, 0)],
        [(0, 1)],
        timeout=timeout,
    )

    assert result is None
    
def test_parse_duplicate_timestep_rejected():
    result = """solved=1
solution=
0:(0,0),
0:(1,0),
"""
    with pytest.raises(Exception, match="Duplicate timestep"):
        _parse_result(result, 1)


def test_parse_missing_timestep_rejected():
    result = """solved=1
solution=
0:(0,0),
2:(2,0),
"""
    with pytest.raises(Exception, match="missing timesteps"):
        _parse_result(result, 1)


@pytest.mark.parametrize(
    "coordinate_line",
    [
        "0:(0,0)garbage,",
        "0:(0,0),,(1,1),",
        "0:(0,0)(1,1),",
        "0:(0,0),(1,1,",
        "0:abc",
    ],
)
def test_parse_malformed_coordinates_rejected(coordinate_line):
    result = f"solved=1\nsolution=\n{coordinate_line}\n"
    with pytest.raises(Exception):
        _parse_result(result, 1)


def test_parse_wrong_agent_count_rejected():
    result = """solved=1
solution=
0:(0,0),(1,1),
"""
    with pytest.raises(Exception, match="expected 1 positions"):
        _parse_result(result, 1)
        
def test_probe_binary_resolves_relative_environment_path(
    tmp_path, monkeypatch
):
    binary = tmp_path / "relative" / "main.exe"
    binary.parent.mkdir()
    binary.touch()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LACAM3_BINARY_PATH", "relative/main.exe")

    result = adapter._probe_binary()

    assert result == binary.resolve()
    
def test_parse_result_preserves_waits_but_metrics_use_individual_arrival():
    result = """solved=1
solution=
0:(0,0),(0,1),(0,2),(0,3),
1:(1,0),(1,1),(1,2),(1,3),
2:(2,0),(2,1),(2,2),(2,3),
3:(2,0),(2,1),(2,2),(3,3),
4:(2,0),(2,1),(2,2),(4,3),
5:(2,0),(2,1),(2,2),(5,3),
6:(2,0),(2,1),(2,2),(6,3),
7:(2,0),(2,1),(2,2),(7,3),
8:(2,0),(2,1),(2,2),(8,3),
9:(2,0),(2,1),(2,2),(9,3),
10:(2,0),(2,1),(2,2),(10,3),
"""

    paths = _parse_result(result, 4)

    assert [len(path) - 1 for path in paths] == [10, 10, 10, 10]

    assert oracle_metrics(paths) == {
        "makespan": 10,
        "SoC": 16,
    }


@pytest.fixture
def solver_output(monkeypatch, tmp_path):
    """Exercise real map/scenario writing, parsing and validation with stub output."""
    import subprocess

    calls = []
    monkeypatch.setattr(adapter, "_probe_binary", lambda: tmp_path / "main.exe")

    def provide(text):
        def run(command, **kwargs):
            calls.append(command)
            assert Path(command[command.index("--map") + 1]).is_file()
            assert Path(command[command.index("--scen") + 1]).is_file()
            Path(command[command.index("--output") + 1]).write_text(text, encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        monkeypatch.setattr(adapter.subprocess, "run", run)
        return calls

    return provide


def test_oracle_solve_preserves_goal_revisit_for_validation(solver_output):
    calls = solver_output("""solved=1
solution=
0:(1,0),(3,0),
1:(2,0),(3,0),
2:(2,1),(2,0),
3:(2,1),(1,0),
4:(2,0),(0,0),
""")
    paths = oracle_solve([[0, 0, 0, 0], [1, 1, 0, 1]],
                         [(0, 1), (0, 3)], [(0, 2), (0, 0)])
    assert len(calls) == 1
    assert paths == [
        [(0, 1), (0, 2), (1, 2), (1, 2), (0, 2)],
        [(0, 3), (0, 3), (0, 2), (0, 1), (0, 0)],
    ]
    assert oracle_metrics(paths) == {"makespan": 4, "SoC": 5}


@pytest.mark.parametrize("tail", ["2:(2,0),\n", "2:(9,0),\n3:(1,0),\n"])
def test_oracle_solve_validates_movement_after_first_goal_visit(solver_output, tail):
    calls = solver_output("solved=1\nsolution=\n0:(0,0),\n1:(1,0),\n" + tail)
    assert oracle_solve([[0, 0, 0]], [(0, 0)], [(0, 1)]) is None
    assert len(calls) == 1
