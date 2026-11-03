"""Matched instances, configs, measurement-only recording, failures and output files."""

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from decentralized_mapf import (DCMAPFPlanner, GlobalCommunication, KNNCommunication, Metrics,
                                NoCommunication, PerfectChannel, RangeCommunication, run_episode)
from decentralized_mapf import harness
from decentralized_mapf.harness import (MAP_TYPES, build_run, equivalence_notes, load_config,
                                        make_instance, make_topology, run_one, run_sweep,
                                        topology_parameter)

ROOT = Path(__file__).resolve().parents[1]
TINY = ("name: tiny\nkind: ladder\nmaps: [warehouse]\nn_agents: [4]\nseeds: [1, 2]\n"
        "topologies: [global, none]\nmax_steps: 16\n")


def write_config(tmp_path, text=TINY):
    path = tmp_path / "tiny.yaml"
    path.write_text(text)
    return path


def test_topology_names():
    assert isinstance(make_topology("global"), GlobalCommunication)
    assert isinstance(make_topology("none"), NoCommunication)
    assert make_topology("range_3").r == 3
    assert make_topology("range_inf").r == float("inf")
    assert isinstance(make_topology("range_3"), RangeCommunication)
    assert isinstance(make_topology("knn_2"), KNNCommunication) and make_topology("knn_2").k == 2
    assert [topology_parameter(n) for n in ("global", "range_5", "knn_1")] == [None, 5, 1]
    for name in ("range", "knn_x", "ring_2"):
        with pytest.raises(ValueError):
            make_topology(name)


@pytest.mark.parametrize("map_name", MAP_TYPES)
@pytest.mark.parametrize("size", [16, 23, 32])
def test_instances_are_reproducible_and_valid(map_name, size):
    instance = make_instance(map_name, 8, seed=3, size=size)
    assert instance == make_instance(map_name, 8, seed=3, size=size)
    grid = instance["grid"]
    assert len(grid) == size and all(len(r) == size for r in grid)
    for r, c in instance["starts"] + instance["goals"]:
        assert grid[r][c] == 0
    assert len(set(instance["starts"])) == len(set(instance["goals"])) == 8
    assert instance["instance_id"] != make_instance(map_name, 8, seed=4, size=size)["instance_id"]


def test_recording_does_not_change_the_run():
    instance = make_instance("random", 10, seed=2)
    row, details = run_one(instance, "global", max_steps=40)

    env, comm, planner = build_run(instance, "global", 40)
    try:
        env.reset(seed=2)
        goals = env.unwrapped.get_targets_xy(ignore_borders=True)
        metrics = Metrics(goals, seed=2, intent_provider=planner.intended_steps)
        summary = run_episode(env, comm, PerfectChannel(), planner, metrics, 40)
    finally:
        env.close()
    assert details["summary"] == summary
    assert details["raw"] == metrics.to_data()
    assert row["ISR"] == summary["ISR"] and isinstance(planner, DCMAPFPlanner)


def test_outcome_separates_solved_from_time_limit():
    instance = make_instance("maze", 10, seed=1)
    solved, _ = run_one(instance, "global", max_steps=256)
    cut, _ = run_one(instance, "global", max_steps=5)
    assert solved["outcome"] == "solved" and solved["SoC"] is not None
    assert cut["outcome"] == "time_limit" and cut["SoC"] is None and cut["steps"] == 5


@pytest.mark.parametrize("extra, message", [
    ("colour: red\n", "unknown keys"),
    ("size: [16, 32]\n", "has 2 values"),
    ("oracle: true\noracle_timeout: 1\nwindow: 0\n", None),
])
def test_config_checks(tmp_path, extra, message):
    path = write_config(tmp_path, TINY + extra)
    if message is None:
        assert load_config(path)["size"] == [32]
    else:
        with pytest.raises(ValueError, match=message):
            load_config(path)


def test_config_rejects_bad_names_and_repeated_seeds(tmp_path):
    for old, new in (("[global, none]", "[global, ring_2]"), ("[warehouse]", "[city]"),
                     ("[1, 2]", "[1, 1]")):
        with pytest.raises(ValueError):
            load_config(write_config(tmp_path, TINY.replace(old, new)))


def test_equivalent_settings_are_noted(tmp_path):
    text = TINY.replace("[global, none]", "[knn_3, knn_2, range_62, range_8]")
    notes = equivalence_notes(load_config(write_config(tmp_path, text)))
    assert notes == ["knn_3 equals global when N = 4", "range_62 equals global on a 32 x 32 map"]


def test_sweep_files_matching_and_no_overwrite(tmp_path, monkeypatch):
    monkeypatch.delenv("LACAM3_BINARY_PATH", raising=False)
    monkeypatch.setattr(harness, "oracle_available", lambda: False)
    out = tmp_path / "out"
    rows = run_sweep(write_config(tmp_path, TINY + "oracle: true\nsave_traces: true\n"), out)
    assert len(rows) == 4
    assert {p.name for p in out.iterdir()} == {"config.yaml", "metadata.json", "instances.json",
                                               "results.jsonl", "results.csv", "traces"}
    with open(out / "results.csv", encoding="utf-8") as file:
        saved = list(csv.DictReader(file))
    assert [(r["seed"], r["topology"]) for r in saved] == [
        ("1", "global"), ("1", "none"), ("2", "global"), ("2", "none")]
    assert {r["oracle_status"] for r in saved} == {"unavailable"}
    # Both topologies of one seed ran on the same map, starts and goals.
    for seed in ("1", "2"):
        assert len({r["instance_id"] for r in saved if r["seed"] == seed}) == 1
    metadata = json.loads((out / "metadata.json").read_text())
    assert metadata["n_runs"] == 4 and metadata["n_errors"] == 0
    assert metadata["versions"]["pogema"]
    assert len(json.loads((out / "instances.json").read_text())) == 2
    assert len(list((out / "traces").glob("*.json"))) == 4
    with pytest.raises(FileExistsError):
        run_sweep(write_config(tmp_path), out)


def test_a_crashing_run_becomes_an_error_row(tmp_path, monkeypatch):
    real = harness.run_one

    def crash_without_messages(instance, topology, **settings):
        if topology == "none":
            raise RuntimeError("planner exploded")
        return real(instance, topology, **settings)

    monkeypatch.setattr(harness, "run_one", crash_without_messages)
    rows = run_sweep(write_config(tmp_path), tmp_path / "out")
    errors = [r for r in rows if r["outcome"] == "error"]
    assert len(errors) == 2 and errors[0]["error"] == "RuntimeError: planner exploded"
    assert all(r["outcome"] != "error" for r in rows if r["topology"] == "global")
    metadata = json.loads((tmp_path / "out" / "metadata.json").read_text())
    assert metadata["n_errors"] == 2


def test_analysis_and_plots_run_on_a_finished_sweep(tmp_path):
    out = tmp_path / "out"
    run_sweep(write_config(tmp_path), out)
    for script in ("analyze.py", "plot_results.py"):
        subprocess.run([sys.executable, str(ROOT / "scripts" / "experiments" / script), str(out)],
                       check=True, capture_output=True)
    assert (out / "checks.txt").read_text() == "All invariants hold.\n"
    assert {p.name for p in (out / "figures").iterdir()} == {
        "1_success_with_and_without_communication.png",
        "2_gain_from_communication_per_instance.png", "3_how_far_stuck_robots_stopped.png",
        "4_cost_on_instances_all_settings_solved.png", "5_robots_at_goal_over_time.png"}
