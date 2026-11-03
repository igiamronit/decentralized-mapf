"""Aggregation, paired comparisons and sanity checks over sweep results (C7).

The experimental unit is one instance (map, starts, goals). Robots inside one
episode share that instance, so they are not independent replicates; every
mean and interval here is taken over instances, one value per instance.
"""

import csv
import json
import math
from pathlib import Path

import numpy as np

BOOTSTRAP_SAMPLES = 10_000


def parse(text):
    """CSV text back to a number, bool or None."""
    if text in ("", "None"):
        return None
    if text in ("True", "False"):
        return text == "True"
    try:
        number = float(text)
    except ValueError:
        return text
    return int(number) if number.is_integer() and "." not in text and "e" not in text else number


# Hex ids such as '3272096e1995' would otherwise parse as numbers in e-notation.
TEXT_COLUMNS = {"experiment", "map", "instance_id", "topology", "family", "outcome", "error",
                "oracle_status", "liveness_definition", "cost_definition"}


def load_results(folder):
    with open(Path(folder) / "results.csv", encoding="utf-8") as file:
        rows = [{key: text if key in TEXT_COLUMNS else parse(text) for key, text in row.items()}
                for row in csv.DictReader(file)]
    for row in rows:
        row["arrival_steps"] = json.loads(row["arrival_steps"]) if row.get("arrival_steps") else None
    return rows


def select(rows, **conditions):
    return [r for r in rows if all(r.get(key) == wanted for key, wanted in conditions.items())]


def mean_ci(values, level=0.95, seed=0):
    """Mean and percentile bootstrap interval over instances.

    Unknown values are left out and counted, never turned into zeros.
    Returns (mean, low, high, n_used, n_missing); the interval is None for n < 2.
    """
    known = [v for v in values if v is not None]
    missing = len(values) - len(known)
    if not known:
        return None, None, None, 0, missing
    mean = sum(known) / len(known)
    if len(known) < 2:
        return mean, None, None, 1, missing
    rng = np.random.default_rng(seed)
    data = np.asarray(known, dtype=float)
    samples = data[rng.integers(0, len(data), (BOOTSTRAP_SAMPLES, len(data)))].mean(axis=1)
    tail = (1 - level) / 2
    low, high = np.quantile(samples, [tail, 1 - tail])
    return mean, float(low), float(high), len(known), missing


def paired_differences(rows, metric, first, second):
    """Per-instance differences metric(first) - metric(second) on matched instances.

    Instances where either value is unknown are dropped and counted.
    """
    by_instance = {}
    for row in rows:
        if row["topology"] in (first, second) and row.get("outcome") != "error":
            by_instance.setdefault(row["instance_id"], {})[row["topology"]] = row.get(metric)
    differences, dropped = [], 0
    for values in by_instance.values():
        a, b = values.get(first), values.get(second)
        if a is None or b is None:
            dropped += 1
        else:
            differences.append(a - b)
    return differences, dropped


def compare(rows, metric, first, second):
    """Paired summary: mean difference, its interval, and wins/ties/losses for first."""
    differences, dropped = paired_differences(rows, metric, first, second)
    mean, low, high, n, _ = mean_ci(differences)
    return {"metric": metric, "first": first, "second": second, "mean_difference": mean,
            "ci_low": low, "ci_high": high, "n_pairs": n, "n_dropped": dropped,
            "first_higher": sum(d > 0 for d in differences),
            "ties": sum(d == 0 for d in differences),
            "first_lower": sum(d < 0 for d in differences)}


def solved_by_all(rows, topologies):
    """Instances fully solved by every listed topology.

    Costs exist only for solved runs. Averaging each topology over its own
    solved runs would favour weak topologies, which solve only easy instances.
    """
    solved = {}
    for row in rows:
        if row["topology"] in topologies:
            solved.setdefault(row["instance_id"], set())
            if row.get("outcome") == "solved":
                solved[row["instance_id"]].add(row["topology"])
    return {i for i, done in solved.items() if done == set(topologies)}


def check_invariants(rows):
    """Return a list of violated invariants; an empty list means every check passed."""
    problems = []
    instances = {}
    for row in rows:
        name = f"{row['map']} n={row['n_agents']} seed={row['seed']} {row['topology']}"
        key = (row["map"], row["size"], row["n_agents"], row["seed"])
        instances.setdefault(key, set()).add(row["instance_id"])
        if row["outcome"] == "error":
            continue

        def fail(message):
            problems.append(f"{name}: {message}")

        n, isr, csr = row["n_agents"], row["ISR"], row["CSR"]
        arrivals = row["arrival_steps"]
        arrived = [a for a in arrivals if a is not None]
        if not 0 <= isr <= 1:
            fail(f"ISR {isr} outside [0, 1]")
        if csr not in (0, 1):
            fail(f"CSR {csr} is not 0 or 1")
        if (csr == 1) != (isr == 1):
            fail("CSR and ISR disagree on full success")
        if not math.isclose(isr, len(arrived) / n):
            fail(f"ISR {isr} differs from recorded arrivals {len(arrived)}/{n}")
        if row["n_arrived"] != len(arrived):
            fail("n_arrived differs from recorded arrivals")
        if row["rho_reach_mean"] > 0:
            fail("rho_reach is positive")
        if csr == 1 and (row["SoC"] != sum(arrived) or row["makespan"] != max(arrived, default=0)):
            fail("SoC or makespan differ from first arrivals")
        if csr == 0 and (row["SoC"] is not None or row["makespan"] is not None):
            fail("an unsolved run has a cost")
        if row["rho_safe"] is not None and row["rho_safe"] < 0:
            fail("two active robots shared a cell")
        if row["family"] == "none" and row["n_messages"] != 0:
            fail("no-communication run delivered messages")
        if row["delay_mean"] is not None and row["delay_mean"] < 0:
            fail("negative delay")
        if row["n_heard"] > row["n_conflicts"] or row["n_mutual"] > row["n_heard"]:
            fail("heard counts exceed conflicts")
        # A blocker is always within Manhattan distance 2 (see coordination docs).
        if (row["family"] == "global" or (row["family"] == "range" and row["parameter"] >= 2)) \
                and row["n_heard"] != row["n_conflicts"]:
            fail("a blocker within range 2 was not heard")
    for key, ids in instances.items():
        if len(ids) != 1:
            problems.append(f"{key}: topologies ran on different instances {sorted(ids)}")
    all_ids = [i for ids in instances.values() for i in ids]
    if len(set(all_ids)) != len(all_ids):
        problems.append("two different seeds share an instance id")
    return problems
