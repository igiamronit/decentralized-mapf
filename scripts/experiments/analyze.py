"""Check and summarize a finished sweep: python scripts/experiments/analyze.py outputs/experiments/<name>

Writes, next to results.csv:
  checks.txt   invariants that every run must satisfy (empty list = all hold)
  outcomes.csv solved / time_limit / error counts per setting
  summary.csv  mean and 95% bootstrap interval per metric, over instances
  paired.csv   matched-instance differences against the 'none' and 'global' settings
"""

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Let the script run from the repository root without installing the package.
sys.path.insert(0, str(ROOT))

from decentralized_mapf.analysis import (check_invariants, compare, load_results,  # noqa: E402
                                         mean_ci)

METRICS = ["ISR", "CSR", "rho_reach_mean", "rho_live_mean", "SoC", "makespan", "soc_ratio",
           "delay_mean", "blocked_per_robot", "heard_share", "messages_per_agent_per_step",
           "mean_degree", "mean_components", "n_deadlocked", "n_epistemic", "n_rule_failure",
           "n_unattributed", "runtime_s"]
# SoC, makespan and soc_ratio exist only for solved runs; their pairs use only
# instances solved by both settings, and n_pairs says how many that was.
PAIRED_METRICS = ["ISR", "CSR", "rho_reach_mean", "SoC", "makespan", "blocked_per_robot"]


def add_derived(rows):
    for row in rows:
        if row["outcome"] == "error":
            continue
        row["blocked_per_robot"] = row["n_blocked_moves"] / row["n_agents"]
        # No conflicts means nothing could be heard or missed.
        row["heard_share"] = row["n_heard"] / row["n_conflicts"] if row["n_conflicts"] else None


def groups(rows):
    keys = []
    for row in rows:
        key = (row["map"], row["size"], row["n_agents"])
        if key not in keys:
            keys.append(key)
    return keys


def write(path, records):
    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()

    rows = load_results(args.folder)
    add_derived(rows)
    topologies = list(dict.fromkeys(r["topology"] for r in rows))

    problems = check_invariants(rows)
    (args.folder / "checks.txt").write_text(
        "\n".join(problems) if problems else "All invariants hold.\n", encoding="utf-8")
    print(f"{len(rows)} runs, {len(problems)} invariant violations")
    for problem in problems[:20]:
        print("  ", problem)

    outcomes, summary, paired = [], [], []
    for map_name, size, n in groups(rows):
        group = [r for r in rows if (r["map"], r["size"], r["n_agents"]) == (map_name, size, n)]
        for topology in topologies:
            runs = [r for r in group if r["topology"] == topology]
            counts = {o: sum(r["outcome"] == o for r in runs)
                      for o in ("solved", "time_limit", "unfinished", "error")}
            outcomes.append({"map": map_name, "size": size, "n_agents": n,
                             "topology": topology, **counts})
            ok = [r for r in runs if r["outcome"] != "error"]
            for metric in METRICS:
                mean, low, high, used, missing = mean_ci([r.get(metric) for r in ok])
                summary.append({"map": map_name, "size": size, "n_agents": n,
                                "topology": topology, "metric": metric, "mean": mean,
                                "ci_low": low, "ci_high": high, "n_instances": used,
                                "n_missing": missing})
        for reference in ("none", "global"):
            if reference not in topologies:
                continue
            for topology in topologies:
                # global vs none is already compared against 'none'.
                if topology == reference or (reference == "global" and topology == "none"):
                    continue
                for metric in PAIRED_METRICS:
                    paired.append({"map": map_name, "size": size, "n_agents": n,
                                   **compare(group, metric, topology, reference)})

    write(args.folder / "outcomes.csv", outcomes)
    write(args.folder / "summary.csv", summary)
    if paired:
        write(args.folder / "paired.csv", paired)
    print(f"wrote checks.txt, outcomes.csv, summary.csv{', paired.csv' if paired else ''} "
          f"in {args.folder}")


if __name__ == "__main__":
    main()
