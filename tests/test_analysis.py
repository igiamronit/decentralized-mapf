"""Aggregation over instances, paired comparisons and invariant checks."""

import json

from decentralized_mapf.analysis import (check_invariants, compare, mean_ci,
                                         paired_differences, solved_by_all)


def run(instance, topology, **values):
    """A valid result row for a 2-robot instance where both robots arrive at t = 3, 4."""
    row = {"map": "random", "size": 32, "n_agents": 2, "seed": int(instance[-1]),
           "instance_id": instance, "topology": topology, "family": topology.split("_")[0],
           "parameter": None, "outcome": "solved", "ISR": 1.0, "CSR": 1.0, "n_arrived": 2,
           "arrival_steps": [3, 4], "SoC": 7, "makespan": 4, "rho_reach_mean": 0.0,
           "rho_safe": 1, "n_messages": 6, "delay_mean": 0.0, "n_conflicts": 0,
           "n_heard": 0, "n_mutual": 0}
    row.update(values)
    return row


def unsolved(instance, topology, **values):
    failed = {"outcome": "time_limit", "ISR": 0.5, "CSR": 0.0, "n_arrived": 1,
              "arrival_steps": [3, None], "SoC": None, "makespan": None,
              "rho_reach_mean": -2.0}
    return run(instance, topology, **{**failed, **values})


def test_mean_ci_counts_missing_and_is_deterministic():
    mean, low, high, n, missing = mean_ci([1.0, None, 3.0, 2.0])
    assert (mean, n, missing) == (2.0, 3, 1)
    assert low <= mean <= high
    assert mean_ci([1.0, None, 3.0, 2.0]) == (mean, low, high, n, missing)
    assert mean_ci([5.0]) == (5.0, None, None, 1, 0)
    assert mean_ci([None, None]) == (None, None, None, 0, 2)
    # Identical values give no spread to resample.
    assert mean_ci([0.5] * 10)[1:3] == (0.5, 0.5)


def test_paired_differences_match_instances_and_drop_unknowns():
    rows = [run("i1", "global", ISR=1.0), unsolved("i1", "none"),
            run("i2", "global"), run("i2", "none"),
            run("i3", "global", outcome="error", ISR=None), run("i3", "none")]
    differences, dropped = paired_differences(rows, "ISR", "global", "none")
    assert sorted(differences) == [0.0, 0.5] and dropped == 1
    # SoC exists only where both solved: instance i2.
    assert paired_differences(rows, "SoC", "global", "none") == ([0], 2)
    summary = compare(rows, "ISR", "global", "none")
    assert (summary["first_higher"], summary["ties"], summary["first_lower"]) == (1, 1, 0)
    assert summary["mean_difference"] == 0.25 and summary["n_pairs"] == 2


def test_solved_by_all_needs_every_setting():
    rows = [run("i1", "global"), unsolved("i1", "none"), run("i2", "global"), run("i2", "none")]
    assert solved_by_all(rows, ["global", "none"]) == {"i2"}
    assert solved_by_all(rows, ["global"]) == {"i1", "i2"}


def test_valid_rows_pass_every_invariant():
    assert check_invariants([run("i1", "global"), unsolved("i1", "none", n_messages=0)]) == []


def test_each_broken_invariant_is_reported():
    broken = [
        run("i1", "global", ISR=1.5),
        run("i1", "global", CSR=0.5),
        run("i1", "global", CSR=0.0),
        run("i1", "global", n_arrived=1),
        run("i1", "global", SoC=8),
        unsolved("i1", "global", SoC=10),
        run("i1", "global", rho_reach_mean=0.5),
        run("i1", "global", rho_safe=-1),
        run("i1", "none", n_messages=3),
        run("i1", "global", delay_mean=-1.0),
        run("i1", "global", n_conflicts=4, n_heard=3, n_mutual=3),
        run("i1", "range_2", parameter=2, n_conflicts=4, n_heard=3, n_mutual=3),
    ]
    for row in broken:
        assert check_invariants([row]), row
    # The same seed must give the same instance under every topology.
    assert check_invariants([run("i1", "global"), run("x1", "range_1", parameter=1)])
    # Two seeds must never collapse into one instance.
    second_seed = run("i1", "global")
    second_seed["seed"] = 2
    assert check_invariants([run("i1", "global"), second_seed])


def test_range_one_may_miss_a_blocker_two_cells_away():
    row = run("i1", "range_1", parameter=1, n_conflicts=4, n_heard=3, n_mutual=3)
    assert check_invariants([row]) == []


def test_rows_survive_a_json_round_trip():
    row = run("i1", "global")
    assert check_invariants([json.loads(json.dumps(row))]) == []


def test_hex_instance_ids_stay_text(tmp_path):
    from decentralized_mapf.analysis import load_results
    (tmp_path / "results.csv").write_text(
        "instance_id,topology,ISR,arrival_steps\n3272096e1995,global,1.0,[1]\n"
        "1e5,none,0.5,[null]\n")
    rows = load_results(tmp_path)
    assert [r["instance_id"] for r in rows] == ["3272096e1995", "1e5"]
    assert rows[0]["ISR"] == 1.0 and rows[1]["arrival_steps"] == [None]
