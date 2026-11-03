"""Figures for a finished sweep: python scripts/experiments/plot_results.py outputs/experiments/<name>

Every point or bar is a mean over instances; error bars are 95% bootstrap
intervals over instances (robots in one episode are not independent). Unknown
values are left out, never drawn as zero. Figures go to figures/ next to results.csv.
"""

import argparse
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import yaml  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
# Let the script run from the repository root without installing the package.
sys.path.insert(0, str(ROOT))

from decentralized_mapf.analysis import (load_results, mean_ci, paired_differences,  # noqa: E402
                                         solved_by_all)
from decentralized_mapf.coordination import RESPONSES  # noqa: E402
from decentralized_mapf.harness import load_config  # noqa: E402

RESPONSE_COLORS = {"wait": "#4C72B0", "detour": "#55A868",
                   "retreat": "#DD8452", "proceed": "#C44E52"}
SUCCESS_LABELS = {"ISR": "Individual success rate (% of robots)",
                  "CSR": "Complete success rate (% of instances)"}


def colors_for(topologies):
    """One fixed colour per setting, shaded by r or k within a family."""
    colors = {"none": "#9E9E9E", "global": "#5E3C99", "oracle": "#2E8B57"}
    for family, cmap in (("range", "Blues"), ("knn", "Oranges")):
        names = sorted((t for t in topologies if t.startswith(family + "_")),
                       key=lambda t: float(t.split("_")[1]))
        for i, name in enumerate(names):
            colors[name] = plt.get_cmap(cmap)(0.45 + 0.5 * i / max(1, len(names) - 1))
    return colors


def ok_rows(rows):
    return [r for r in rows if r["outcome"] != "error"]


def stat(rows, metric, scale=1.0):
    """(mean, lower error, upper error) for an error bar, or None if no data."""
    mean, low, high, n, _ = mean_ci([None if r.get(metric) is None else r[metric] * scale
                                     for r in rows])
    if mean is None:
        return None
    if low is None:
        return mean, 0.0, 0.0
    return mean, mean - low, high - mean


def scale_of(metric):
    return 100.0 if metric in SUCCESS_LABELS else 1.0


def grouped_bars(ax, maps, topologies, colors, value, below=False, labels=True):
    """Bars grouped by map, one bar per setting; value(map, topology) -> stat or None.

    below=True writes value labels under the bars, for metrics that are never positive.
    """
    width = 0.8 / len(topologies)
    for j, topology in enumerate(topologies):
        for i, map_name in enumerate(maps):
            s = value(map_name, topology)
            x = i + (j - (len(topologies) - 1) / 2) * width
            if s is None:
                ax.text(x, 0, "n/a", ha="center", va="bottom", fontsize=7)
                continue
            ax.bar(x, s[0], width, yerr=[[s[1]], [s[2]]], capsize=3, color=colors[topology],
                   label=topology if i == 0 else None)
            if labels:
                ax.text(x, s[0] - s[1] if below else s[0] + s[2], f"{s[0]:.1f}", ha="center",
                        va="top" if below else "bottom", fontsize=7)
    ax.set_xticks(range(len(maps)), maps)
    ax.set_xlabel("map type")
    ax.margins(y=0.12)


def save(fig, folder, name):
    if not fig.legends:
        fig.tight_layout()
    path = folder / name
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"saved {path}")


# ---------------------------------------------------------------- ladder (E1)

def ladder_figures(rows, config, folder):
    topologies = config["topologies"]
    colors = colors_for(topologies)
    maps = config["maps"]
    n = config["n_agents"][0]
    oracle = any(r.get("oracle_status") in ("solved", "failed", "timeout") for r in rows)
    shown = (["oracle"] if oracle else []) + topologies

    def value(metric):
        def get(map_name, topology):
            group = select_map(rows, map_name)
            if topology == "oracle":
                instances = {r["instance_id"]: r for r in group}.values()
                if metric == "CSR":
                    return stat([{"v": r["oracle_status"] == "solved"} for r in instances],
                                "v", 100.0)
                return None
            return stat([r for r in group if r["topology"] == topology], metric, scale_of(metric))
        return get

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    for ax, metric in zip(axes, ("CSR", "ISR")):
        grouped_bars(ax, maps, shown, colors, value(metric))
        ax.set_ylim(0, 125)
        ax.set_yticks(range(0, 101, 20))
        ax.set_ylabel(SUCCESS_LABELS[metric])
        what = "Complete" if metric == "CSR" else "Individual"
        ax.set_title(f"{what} success rate: global vs no communication (N = {n})")
        ax.legend(fontsize=8, loc="upper right", ncol=len(shown))
    save(fig, folder, "ladder_success.png")

    fig, axes = plt.subplots(1, len(maps), figsize=(4.4 * len(maps), 4.4), sharey=True,
                             squeeze=False)
    axes = axes[0]
    for ax, map_name in zip(axes, maps):
        diffs, dropped = paired_differences(select_map(rows, map_name), "ISR", "global", "none")
        diffs = sorted(100 * d for d in diffs)
        # Spread equal values sideways so every instance stays visible.
        xs = [(diffs[:i].count(d) - (diffs.count(d) - 1) / 2) * 0.035 for i, d in enumerate(diffs)]
        ax.scatter(xs, diffs, s=18, color="#555555", alpha=0.8, label="one instance")
        mean, low, high, k, _ = mean_ci(diffs)
        ax.errorbar([0.25], [mean], yerr=[[mean - low], [high - mean]], fmt="o", color="black",
                    capsize=5, label="mean, 95% CI")
        ax.axhline(0, color="gray", linewidth=0.8)
        better, worse = sum(d > 0 for d in diffs), sum(d < 0 for d in diffs)
        ax.set_title(f"{map_name}: global higher on {better}, equal on {k - better - worse}, "
                     f"lower on {worse}", fontsize=10)
        ax.set_xticks([])
        ax.set_xlim(-0.4, 0.5)
    axes[0].set_ylabel("ISR(global) − ISR(none), same instance (pp)")
    axes[0].legend(fontsize=8)
    fig.suptitle(f"Paired effect of global communication on individual success (N = {n})")
    save(fig, folder, "ladder_paired.png")

    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    grouped_bars(ax, maps, topologies, colors,
                 lambda m, t: stat([r for r in select_map(rows, m) if r["topology"] == t],
                                   "rho_reach_mean"), below=True)
    ax.set_ylabel("Mean ρ_reach (grid cells; 0 = all robots arrived)")
    ax.set_title(f"Goal-reaching robustness: how far short failed robots stopped (N = {n})")
    ax.legend(fontsize=8)
    save(fig, folder, "ladder_reach.png")

    cost_figure(rows, maps, topologies, colors, folder, oracle, n)
    arrival_figure(rows, maps, topologies, colors, folder, config, n)


def select_map(rows, map_name):
    return [r for r in ok_rows(rows) if r["map"] == map_name]


def cost_figure(rows, maps, topologies, colors, folder, oracle, n):
    """Costs only on instances every setting solved, so the comparison is fair."""
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    counts = []
    shown = topologies + (["oracle"] if oracle else [])
    for i, map_name in enumerate(maps):
        group = select_map(rows, map_name)
        common = solved_by_all(group, topologies)
        if oracle:
            common = {r["instance_id"] for r in group
                      if r["instance_id"] in common and r["oracle_status"] == "solved"}
        counts.append(len(common))
        matched = [r for r in group if r["instance_id"] in common]
        width = 0.8 / len(shown)
        for j, topology in enumerate(shown):
            if topology == "oracle":
                instances = {r["instance_id"]: r for r in matched}.values()
                s = stat(list(instances), "oracle_SoC")
            else:
                s = stat([r for r in matched if r["topology"] == topology], "SoC")
            x = i + (j - (len(shown) - 1) / 2) * width
            if s is None or len(common) < 3:
                ax.text(x, 0, "too few", ha="center", va="bottom", fontsize=7, rotation=90)
                continue
            ax.bar(x, s[0], width, yerr=[[s[1]], [s[2]]], capsize=3, color=colors[topology],
                   label=topology if i == 0 else None)
    labels = []
    for map_name, count in zip(maps, counts):
        label = f"{map_name}\n({count} instances)"
        if len(topologies) == 2 and count:
            diffs, _ = paired_differences(
                [r for r in select_map(rows, map_name) if r["outcome"] == "solved"], "SoC",
                topologies[0], topologies[1])
            if diffs and all(d == 0 for d in diffs):
                label += "\npaired difference 0 on all"
        labels.append(label)
    ax.set_xticks(range(len(maps)), labels)
    ax.set_ylabel("Sum of costs (timesteps)")
    ax.set_title(f"Sum of costs on instances solved by every setting (N = {n})")
    ax.legend(fontsize=8)
    save(fig, folder, "ladder_cost.png")


def arrival_figure(rows, maps, topologies, colors, folder, config, n):
    max_steps = config["max_steps"][0]
    steps = list(range(max_steps + 1))
    fig, axes = plt.subplots(1, len(maps), figsize=(4.6 * len(maps), 4.2), sharey=True,
                             squeeze=False)
    axes = axes[0]
    for ax, map_name in zip(axes, maps):
        for topology in topologies:
            runs = [r for r in select_map(rows, map_name) if r["topology"] == topology]
            curves = [[100 * sum(a is not None and a <= t for a in r["arrival_steps"])
                       / r["n_agents"] for t in steps] for r in runs]
            stats = [mean_ci([c[t] for c in curves]) for t in steps]
            ax.plot(steps, [s[0] for s in stats], color=colors[topology], label=topology)
            ax.fill_between(steps, [s[1] for s in stats], [s[2] for s in stats],
                            color=colors[topology], alpha=0.2)
        ax.set_title(f"{map_name}: robots at goal over time")
        ax.set_xlabel("timestep")
        ax.set_ylim(0, 102)
    axes[0].set_ylabel("Robots that have reached their goal (%)")
    axes[0].legend(fontsize=8)
    fig.suptitle(f"Arrival over time (N = {n}; band = 95% CI over instances)")
    save(fig, folder, "ladder_arrivals.png")


# ------------------------------------------------------- topology (E2, E3, E5)

def family_curve(ax, rows, family, x_metric, y_metric, color, label, scale=1.0):
    names = sorted({r["topology"] for r in rows if r["family"] == family},
                   key=lambda t: float(t.split("_")[1]))
    points = []
    for name in names:
        runs = [r for r in rows if r["topology"] == name]
        x = (runs[0]["parameter"] if x_metric == "parameter"
             else mean_ci([r[x_metric] for r in runs])[0])
        s = stat(runs, y_metric, scale)
        if s is not None and x is not None and not math.isinf(x):
            points.append((x, s))
    points.sort()
    ax.errorbar([p[0] for p in points], [p[1][0] for p in points],
                yerr=[[p[1][1] for p in points], [p[1][2] for p in points]],
                marker="o", capsize=3, color=color, label=label)


def reference_band(ax, rows, topology, metric, color, scale=1.0):
    mean, low, high, _, _ = mean_ci([r[metric] * scale for r in rows
                                     if r["topology"] == topology and r[metric] is not None])
    if mean is None:
        return
    ax.axhline(mean, color=color, linestyle="--", linewidth=1.2, label=f"{topology} (95% CI band)")
    if low is not None:
        ax.axhspan(low, high, color=color, alpha=0.1)


def topology_figures(rows, config, folder):
    topologies = config["topologies"]
    colors = colors_for(topologies)
    maps = config["maps"]
    n = config["n_agents"][0]

    fig, axes = plt.subplots(2, len(maps), figsize=(4.8 * len(maps), 8), squeeze=False)
    for col, map_name in enumerate(maps):
        group = select_map(rows, map_name)
        for row_index, (metric, label) in enumerate((
                ("ISR", SUCCESS_LABELS["ISR"]),
                ("rho_reach_mean", "Mean ρ_reach (grid cells; 0 = all arrived)"))):
            ax = axes[row_index][col]
            scale = scale_of(metric)
            family_curve(ax, group, "range", "parameter", metric, "#3A7DBF", "range r", scale)
            for reference in ("global", "none"):
                reference_band(ax, group, reference, metric, colors[reference], scale)
            ax.set_xscale("log", base=2)
            swept = sorted({r["parameter"] for r in group if r["family"] == "range"
                            and not math.isinf(r["parameter"])})
            ax.set_xticks(swept, [str(int(v)) for v in swept])
            ax.minorticks_off()
            ax.set_xlabel("communication range r (Manhattan cells, log scale)")
            ax.set_ylabel(label)
            what = "Individual success" if metric == "ISR" else "Goal-reaching robustness"
            ax.set_title(f"{map_name}: {what} vs range r")
            if metric == "ISR":
                ax.set_ylim(0, 102)
    handles, names = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, names, loc="lower center", ncol=3, fontsize=9)
    fig.suptitle(f"How far must messages carry? (N = {n}, 32 x 32 maps)")
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    save(fig, folder, "topology_range.png")

    fig, axes = plt.subplots(1, len(maps), figsize=(4.8 * len(maps), 4.4), squeeze=False)
    for ax, map_name in zip(axes[0], maps):
        group = select_map(rows, map_name)
        family_curve(ax, group, "range", "mean_degree", "ISR", "#3A7DBF", "range r", 100)
        family_curve(ax, group, "knn", "mean_degree", "ISR", "#E08A3C", "k-NN", 100)
        for reference in ("global", "none"):
            reference_band(ax, group, reference, "ISR", colors[reference], 100)
        ax.set_xscale("log", base=2)
        ax.xaxis.set_major_formatter(matplotlib.ticker.ScalarFormatter())
        ax.set_xlabel("mean talk-graph degree (receivers per robot per step, log)")
        ax.set_ylabel(SUCCESS_LABELS["ISR"])
        ax.set_ylim(0, 102)
        ax.set_title(f"{map_name}: range vs k-NN at equal degree")
    handles, names = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, names, loc="lower center", ncol=4, fontsize=9)
    fig.suptitle(f"Does the structure of the talk graph matter at equal degree? (N = {n})")
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    save(fig, folder, "topology_degree.png")

    fig, axes = plt.subplots(1, len(maps), figsize=(4.8 * len(maps), 4.4), squeeze=False)
    for ax, map_name in zip(axes[0], maps):
        group = select_map(rows, map_name)
        for topology in topologies:
            runs = [r for r in group if r["topology"] == topology]
            x = mean_ci([r["messages_per_agent_per_step"] for r in runs])[0]
            s = stat(runs, "ISR", 100)
            ax.errorbar([x], [s[0]], yerr=[[s[1]], [s[2]]], fmt="o", capsize=3,
                        color=colors[topology], label=topology)
        ax.set_xscale("symlog", linthresh=0.1)
        ax.set_xlabel("delivered messages per robot per step (symlog)")
        ax.set_ylabel(SUCCESS_LABELS["ISR"])
        ax.set_ylim(0, 102)
        ax.set_title(f"{map_name}: communication overhead vs success")
    handles, names = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, names, loc="lower center", ncol=7, fontsize=8)
    fig.suptitle(f"More messages, more success? (N = {n})")
    fig.tight_layout(rect=(0, 0.12, 1, 1))
    save(fig, folder, "topology_overhead.png")

    fig, ax = plt.subplots(figsize=(11, 4.6))
    talking = [t for t in topologies if t != "none"]
    grouped_bars(ax, maps, talking, colors,
                 lambda m, t: stat([r for r in select_map(rows, m)
                                    if r["topology"] == t and r["n_conflicts"]],
                                   "heard_share", 100), labels=False)
    ax.set_ylim(0, 105)
    ax.set_ylabel("Conflicts where the blocker was heard (%)")
    ax.set_title(f"Was the blocking robot's claim delivered? (N = {n}; r ≥ 2 must give 100%)")
    ax.legend(fontsize=8, ncol=6, loc="upper center", bbox_to_anchor=(0.5, -0.14))
    save(fig, folder, "topology_heard.png")

    response_figure(rows, topologies, folder, n)
    stall_figure(rows, maps, topologies, folder, n)


def response_figure(rows, topologies, folder, n):
    """Pooled shares over all maps and instances: descriptive, no interval."""
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6), sharey=True)
    for ax, heard in zip(axes, ("heard", "unheard")):
        bottoms = [0.0] * len(topologies)
        totals = [sum(r[f"n_{resp}_{heard}"] for r in ok_rows(rows) if r["topology"] == t
                      for resp in RESPONSES) for t in topologies]
        for response in RESPONSES:
            shares = [100 * sum(r[f"n_{response}_{heard}"] for r in ok_rows(rows)
                                if r["topology"] == t) / total if total else 0
                      for t, total in zip(topologies, totals)]
            ax.bar(topologies, shares, bottom=bottoms, color=RESPONSE_COLORS[response],
                   label=response)
            bottoms = [b + s for b, s in zip(bottoms, shares)]
        for x, total in enumerate(totals):
            if not total:
                ax.text(x, 2, "no such\nconflicts", ha="center", fontsize=7)
        ax.set_title(f"Response when the blocker was {'heard' if heard == 'heard' else 'not heard'}")
        ax.set_ylabel("Share of conflicts (%)")
        ax.tick_params(axis="x", rotation=45)
    axes[1].legend(fontsize=8, loc="upper right")
    fig.suptitle(f"How robots responded to a blocked claim (N = {n}, pooled over maps and instances)")
    save(fig, folder, "topology_responses.png")


def stall_figure(rows, maps, topologies, folder, n):
    fig, axes = plt.subplots(1, len(maps), figsize=(5.2 * len(maps), 4.6), sharey=True,
                             squeeze=False)
    axes = axes[0]
    causes = (("n_epistemic", "blocker not heard (epistemic)", "#C44E52"),
              ("n_rule_failure", "heard, still stuck (rule failure)", "#4C72B0"),
              ("n_unattributed", "no blocker identified", "#C8C8C8"))
    for ax, map_name in zip(axes, maps):
        group = select_map(rows, map_name)
        bottoms = [0.0] * len(topologies)
        for key, label, color in causes:
            heights = [mean_ci([r[key] for r in group if r["topology"] == t])[0] or 0
                       for t in topologies]
            ax.bar(topologies, heights, bottom=bottoms, color=color, label=label)
            bottoms = [b + h for b, h in zip(bottoms, heights)]
        ax.set_title(f"{map_name}: stalled robots by cause")
        ax.tick_params(axis="x", rotation=60)
    axes[0].set_ylabel("Stalled robots per instance (mean)")
    axes[0].legend(fontsize=8)
    fig.suptitle(f"Why robots stalled (N = {n}; a stall = no progress in a 10-step window)")
    save(fig, folder, "topology_stalls.png")


# ------------------------------------------------------------------ scaling (E4)

def scaling_figures(rows, config, folder):
    topologies = config["topologies"]
    colors = colors_for(topologies)
    maps = config["maps"]
    sizes = dict(zip(config["n_agents"], config["size"]))
    fixed = len(set(config["size"])) == 1
    setting = (f"fixed {config['size'][0]} x {config['size'][0]} map" if fixed
               else "map grows with N, about 0.03 robots per cell")

    def lines(ax, group, metric, scale=1.0):
        for j, topology in enumerate(topologies):
            # Small horizontal offsets and distinct markers keep equal series visible.
            shift = 1.04 ** (j - (len(topologies) - 1) / 2)
            marker = "osD^v"[j % 5]
            ns, stats = [], []
            for n in config["n_agents"]:
                s = stat([r for r in group if r["topology"] == topology and r["n_agents"] == n],
                         metric, scale)
                if s is not None:
                    ns.append(n)
                    stats.append(s)
            ax.errorbar([n * shift for n in ns], [s[0] for s in stats],
                        yerr=[[s[1] for s in stats], [s[2] for s in stats]],
                        marker=marker, capsize=3, color=colors[topology], label=topology)
        ax.set_xscale("log", base=2)
        ax.set_xticks(config["n_agents"],
                      [str(n) if fixed else f"{n}\n({sizes[n]}²)" for n in config["n_agents"]])
        ax.set_xlabel("number of robots N" + ("" if fixed else " (map size)"))

    panels = [("ISR", SUCCESS_LABELS["ISR"], "Individual success"),
              ("CSR", SUCCESS_LABELS["CSR"], "Complete success")]
    fig, axes = plt.subplots(2, len(maps), figsize=(5.2 * len(maps), 8.4), squeeze=False)
    for col, map_name in enumerate(maps):
        for row_index, (metric, label, what) in enumerate(panels):
            ax = axes[row_index][col]
            lines(ax, select_map(rows, map_name), metric, 100)
            ax.set_ylim(0, 105)
            ax.set_ylabel(label)
            ax.set_title(f"{map_name}: {what} as N grows")
    axes[0][0].legend(fontsize=8)
    fig.suptitle(f"Effect of agent count on goal-reaching success ({setting})")
    save(fig, folder, "scaling_success.png")

    panels = [("rho_reach_mean", "Mean ρ_reach (grid cells; 0 = all arrived)",
               "Goal-reaching robustness"),
              ("delay_mean", "Delay of arrived robots (timesteps)",
               "Delay, arrived robots only")]
    fig, axes = plt.subplots(2, len(maps), figsize=(5.2 * len(maps), 8.4), squeeze=False)
    for col, map_name in enumerate(maps):
        for row_index, (metric, label, what) in enumerate(panels):
            ax = axes[row_index][col]
            lines(ax, select_map(rows, map_name), metric)
            ax.set_ylabel(label)
            ax.set_title(f"{map_name}: {what} as N grows")
    axes[0][0].legend(fontsize=8)
    fig.suptitle(f"How far failed robots stop, and how long arrivals wait ({setting})")
    save(fig, folder, "scaling_reach_delay.png")

    fig, axes = plt.subplots(1, len(maps), figsize=(5.2 * len(maps), 4.4), squeeze=False)
    for ax, map_name in zip(axes[0], maps):
        lines(ax, select_map(rows, map_name), "messages_per_agent_per_step")
        ax.set_yscale("symlog", linthresh=0.1)
        ax.set_ylim(bottom=0)
        ax.set_ylabel("Delivered messages per robot per step (symlog)")
        ax.set_title(f"{map_name}: message load as N grows")
    axes[0][0].legend(fontsize=8)
    fig.suptitle(f"Communication overhead vs fleet size ({setting})")
    save(fig, folder, "scaling_messages.png")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", type=Path, help="sweep output folder with results.csv")
    args = parser.parse_args()

    config = load_config(args.folder / "config.yaml")
    rows = load_results(args.folder)
    for row in rows:
        if row["outcome"] != "error":
            row["heard_share"] = row["n_heard"] / row["n_conflicts"] if row["n_conflicts"] else None
    folder = args.folder / "figures"
    folder.mkdir(exist_ok=True)
    {"ladder": ladder_figures, "topology": topology_figures,
     "scaling": scaling_figures}[config["kind"]](rows, config, folder)


if __name__ == "__main__":
    main()
