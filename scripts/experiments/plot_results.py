"""Figures for a finished sweep: python scripts/experiments/plot_results.py outputs/experiments/<name>

Every point or bar is a mean over instances; error bars are 95% bootstrap
intervals over instances (robots in one episode are not independent). Unknown
values are left out, never drawn as zero. Figures go to figures/ next to
results.csv, numbered in reading order.
"""

import argparse
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
# Let the script run from the repository root without installing the package.
sys.path.insert(0, str(ROOT))

from decentralized_mapf.analysis import (load_results, mean_ci, paired_differences,  # noqa: E402
                                         solved_by_all)
from decentralized_mapf.harness import load_config  # noqa: E402
from figure_style import (KNN_COLOR, KNN_SHADES, QUIET_GREY, RANGE_COLOR,  # noqa: E402
                          RANGE_SHADES, RESPONSE_COLORS, SETTING_COLORS, apply)

SUCCESS_LABELS = {"ISR": "Robots that reached their goal (%)",
                  "CSR": "Instances fully solved (%)"}
REACH_LABEL = "Mean ρ_reach (cells; 0 = all arrived)"
ERROR_STYLE = {"elinewidth": 1, "capthick": 1}
# Crowded figures show these settings only, when the sweep has them.
FEATURED = ["none", "range_1", "range_2", "range_5", "knn_1", "knn_2", "knn_4", "global"]


def colors_for(topologies):
    """One fixed colour per setting, shaded by r or k within a family."""
    colors = dict(SETTING_COLORS)
    for family, shades in (("range", RANGE_SHADES), ("knn", KNN_SHADES)):
        names = sorted((t for t in topologies if t.startswith(family + "_")),
                       key=lambda t: float(t.split("_")[1]))
        for i, name in enumerate(names):
            colors[name] = shades(0.25 + 0.75 * i / max(1, len(names) - 1))
    return colors


def ok_rows(rows):
    return [r for r in rows if r["outcome"] != "error"]


def select_map(rows, map_name):
    return [r for r in ok_rows(rows) if r["map"] == map_name]


def stat(rows, metric, scale=1.0):
    """(mean, lower error, upper error) for an error bar, or None if no data."""
    mean, low, high, _, _ = mean_ci([None if r.get(metric) is None else r[metric] * scale
                                     for r in rows])
    if mean is None:
        return None
    if low is None:
        return mean, 0.0, 0.0
    return mean, mean - low, high - mean


def scale_of(metric):
    return 100.0 if metric in SUCCESS_LABELS else 1.0


def featured(topologies):
    chosen = [t for t in FEATURED if t in topologies]
    return chosen if len(chosen) >= 3 else list(topologies)


def grouped_bars(ax, maps, topologies, colors, value, below=False):
    """Bars grouped by map, one bar per setting; value(map, topology) -> stat or None.

    below=True writes value labels under the bars, for metrics that are never positive.
    """
    width = 0.8 / len(topologies)
    for j, topology in enumerate(topologies):
        for i, map_name in enumerate(maps):
            s = value(map_name, topology)
            x = i + (j - (len(topologies) - 1) / 2) * width
            if s is None:
                ax.text(x, 0, "n/a", ha="center", va="bottom", fontsize=8, color="#777777")
                continue
            ax.bar(x, s[0], width * 0.92, yerr=[[s[1]], [s[2]]], color=colors[topology],
                   error_kw={**ERROR_STYLE, "ecolor": "#444444"},
                   label=topology if i == 0 else None)
            ax.text(x, s[0] - s[1] if below else s[0] + s[2], f"{s[0]:.1f}", ha="center",
                    va="top" if below else "bottom", fontsize=8, color="#444444")
    ax.set_xticks(range(len(maps)), maps)
    ax.tick_params(axis="x", length=0)
    ax.margins(y=0.12)


def line(ax, xs, stats, color, marker, label):
    """A mean line with thin 95% interval bars; stats are (mean, lower, upper) errors."""
    ax.errorbar(xs, [s[0] for s in stats], yerr=[[s[1] for s in stats], [s[2] for s in stats]],
                marker=marker, color=color, label=label, **ERROR_STYLE)


def log2_axis(ax, ticks):
    ax.set_xscale("log", base=2)
    ax.set_xticks(ticks, [str(int(t)) for t in ticks])
    ax.minorticks_off()


def save(fig, folder, name, legend_space=0.0):
    fig.tight_layout(rect=(0, legend_space, 1, 1))
    path = folder / name
    fig.savefig(path)
    plt.close(fig)
    print(f"saved {path}")


def bottom_legend(fig, ax, ncol):
    handles, names = ax.get_legend_handles_labels()
    fig.legend(handles, names, loc="lower center", ncol=ncol)


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
                # A solved oracle plan brings every robot home.
                return stat([{"v": r["oracle_status"] == "solved"} for r in instances
                             if r["oracle_status"] in ("solved", "failed", "timeout")], "v", 100.0)
            return stat([r for r in group if r["topology"] == topology], metric, scale_of(metric))
        return get

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    for ax, metric in zip(axes, ("CSR", "ISR")):
        grouped_bars(ax, maps, shown, colors, value(metric))
        ax.set_ylim(0, 112)
        ax.set_yticks(range(0, 101, 20))
        ax.set_ylabel(SUCCESS_LABELS[metric])
        ax.set_title("Instances fully solved" if metric == "CSR" else "Robots at their goal")
    bottom_legend(fig, axes[0], len(shown))
    fig.suptitle(f"Does communication help? ({n} robots)")
    save(fig, folder, "1_success_with_and_without_communication.png", 0.07)

    fig, axes = plt.subplots(1, len(maps), figsize=(4.2 * len(maps), 4.4), sharey=True,
                             squeeze=False)
    for ax, map_name in zip(axes[0], maps):
        diffs, _ = paired_differences(select_map(rows, map_name), "ISR", "global", "none")
        diffs = sorted(100 * d for d in diffs)
        # Spread equal values sideways so every instance stays visible.
        xs = [(diffs[:i].count(d) - (diffs.count(d) - 1) / 2) * 0.035 for i, d in enumerate(diffs)]
        ax.scatter(xs, diffs, s=20, color=colors["global"], alpha=0.55, linewidths=0,
                   label="one instance")
        mean, low, high, k, _ = mean_ci(diffs)
        ax.errorbar([0.3], [mean], yerr=[[mean - low], [high - mean]], fmt="o", color="black",
                    label="mean, 95% CI", **ERROR_STYLE)
        ax.axhline(0, color="#999999", linewidth=0.8)
        better, worse = sum(d > 0 for d in diffs), sum(d < 0 for d in diffs)
        ax.set_title(f"{map_name}: {mean:+.1f} pp")
        ax.set_xlabel(f"higher {better} · equal {k - better - worse} · lower {worse}")
        ax.set_xticks([])
        ax.set_xlim(-0.4, 0.55)
    axes[0][0].set_ylabel("ISR(global) − ISR(none), same instance (pp)")
    axes[0][0].legend(loc="upper left")
    fig.suptitle(f"Gain from global communication on each instance ({n} robots)")
    save(fig, folder, "2_gain_from_communication_per_instance.png")

    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    grouped_bars(ax, maps, topologies, colors,
                 lambda m, t: stat([r for r in select_map(rows, m) if r["topology"] == t],
                                   "rho_reach_mean"), below=True)
    ax.axhline(0, color="#888888", linewidth=0.8)
    ax.set_ylabel(REACH_LABEL)
    ax.legend(loc="lower left")
    ax.set_title(f"How far short stuck robots stopped ({n} robots)")
    save(fig, folder, "3_how_far_stuck_robots_stopped.png")

    cost_figure(rows, maps, topologies, colors, folder, oracle, n)
    arrival_figure(rows, maps, topologies, colors, folder, config, n)


def oracle_ratio_figure(rows, maps, topologies, colors, folder, n):
    """Per-instance SoC(ours) / SoC(LaCAM3), each setting on the instances it solved.

    Pairing with the oracle on the same instance removes the large differences
    between instances. Each setting keeps all its solved instances, so a setting
    that solves only easy instances shows a low ratio; the solved count says so.
    """
    fig, axes = plt.subplots(1, len(maps), figsize=(4.4 * len(maps), 4.6), sharey=True,
                             squeeze=False)
    for ax, map_name in zip(axes[0], maps):
        group = select_map(rows, map_name)
        n_instances = len({r["instance_id"] for r in group})
        labels = []
        for x, topology in enumerate(topologies):
            ratios = sorted(r["soc_ratio"] for r in group
                            if r["topology"] == topology and r["soc_ratio"] is not None)
            offsets = [((i % 7) - 3) * 0.04 for i in range(len(ratios))]
            ax.scatter([x - 0.15 + o for o in offsets], ratios, s=16, alpha=0.55, linewidths=0,
                       color=colors[topology])
            mean, low, high, k, _ = mean_ci(ratios)
            if mean is not None:
                ax.errorbar([x + 0.25], [mean], yerr=[[mean - (low or mean)], [(high or mean) - mean]],
                            fmt="o", color="black", **ERROR_STYLE)
                ax.text(x + 0.33, mean, f"{mean:.3f}", va="center", fontsize=8, color="#333333")
            labels.append(f"{topology}\nsolved {k}/{n_instances}")
        ax.axhline(1, color=colors["oracle"], linestyle="--", linewidth=1.2, label="LaCAM3 = 1")
        ax.set_xticks(range(len(topologies)), labels)
        ax.tick_params(axis="x", length=0)
        ax.set_xlim(-0.6, len(topologies) - 0.3)
        ax.margins(y=0.15)
        ax.set_title(map_name)
    axes[0][0].set_ylabel("SoC ÷ LaCAM3 SoC, same instance")
    axes[0][0].legend(loc="upper left")
    fig.suptitle(f"Extra cost over the centralized plan ({n} robots)")
    save(fig, folder, "4_cost_compared_with_oracle.png")


def cost_figure(rows, maps, topologies, colors, folder, oracle, n):
    """Costs only on instances every setting solved, so the comparison is fair."""
    if oracle:
        oracle_ratio_figure(rows, maps, topologies, colors, folder, n)
        return
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    counts = []
    for i, map_name in enumerate(maps):
        group = select_map(rows, map_name)
        common = solved_by_all(group, topologies)
        counts.append(len(common))
        matched = [r for r in group if r["instance_id"] in common]
        width = 0.8 / len(topologies)
        for j, topology in enumerate(topologies):
            s = stat([r for r in matched if r["topology"] == topology], "SoC")
            x = i + (j - (len(topologies) - 1) / 2) * width
            if s is None or len(common) < 3:
                ax.text(x, 0, "too few", ha="center", va="bottom", fontsize=8, rotation=90)
                continue
            ax.bar(x, s[0], width * 0.92, yerr=[[s[1]], [s[2]]], color=colors[topology],
                   error_kw={**ERROR_STYLE, "ecolor": "#444444"},
                   label=topology if i == 0 else None)
    labels = []
    for map_name, count in zip(maps, counts):
        label = f"{map_name}\n{count} instances"
        if len(topologies) == 2 and count:
            diffs, _ = paired_differences(
                [r for r in select_map(rows, map_name) if r["outcome"] == "solved"], "SoC",
                topologies[0], topologies[1])
            if diffs and all(d == 0 for d in diffs):
                label += "\nidentical on every one"
        labels.append(label)
    ax.set_xticks(range(len(maps)), labels)
    ax.tick_params(axis="x", length=0)
    ax.set_ylabel("Sum of costs (timesteps)")
    ax.set_title(f"Total cost where every setting succeeded ({n} robots)")
    ax.legend(loc="lower right")
    save(fig, folder, "4_cost_on_instances_all_settings_solved.png")


def arrival_figure(rows, maps, topologies, colors, folder, config, n):
    max_steps = config["max_steps"][0]
    steps = list(range(max_steps + 1))
    fig, axes = plt.subplots(1, len(maps), figsize=(4.4 * len(maps), 4.2), sharey=True,
                             squeeze=False)
    for ax, map_name in zip(axes[0], maps):
        for topology in topologies:
            runs = [r for r in select_map(rows, map_name) if r["topology"] == topology]
            curves = [[100 * sum(a is not None and a <= t for a in r["arrival_steps"])
                       / r["n_agents"] for t in steps] for r in runs]
            stats = [mean_ci([c[t] for c in curves]) for t in steps]
            ax.plot(steps, [s[0] for s in stats], color=colors[topology], label=topology)
            ax.fill_between(steps, [s[1] for s in stats], [s[2] for s in stats],
                            color=colors[topology], alpha=0.15, linewidth=0)
        ax.set_title(map_name)
        ax.set_xlabel("timestep")
        ax.set_ylim(0, 102)
    axes[0][0].set_ylabel("Robots at their goal (%)")
    axes[0][0].legend(loc="lower right")
    fig.suptitle(f"Robots at goal over time ({n} robots; band = 95% CI)")
    save(fig, folder, "5_robots_at_goal_over_time.png")


# ------------------------------------------------------- topology (E2, E3, E5)

def family_points(rows, family, x_metric, y_metric, scale=1.0):
    """(x, mean, lower error, upper error, parameter) for each r or k in one family."""
    names = sorted({r["topology"] for r in rows if r["family"] == family},
                   key=lambda t: float(t.split("_")[1]))
    points = []
    for name in names:
        runs = [r for r in rows if r["topology"] == name]
        x = (runs[0]["parameter"] if x_metric == "parameter"
             else mean_ci([r[x_metric] for r in runs])[0])
        s = stat(runs, y_metric, scale)
        if s is not None and x is not None and not math.isinf(x):
            points.append((x, *s, runs[0]["parameter"]))
    return sorted(points)


def family_curve(ax, rows, family, x_metric, y_metric, color, label, scale=1.0, marker="o"):
    points = family_points(rows, family, x_metric, y_metric, scale)
    line(ax, [p[0] for p in points], [p[1:4] for p in points], color, marker, label)
    return points


def reference_band(ax, rows, topology, metric, color, scale=1.0):
    mean, low, high, _, _ = mean_ci([r[metric] * scale for r in rows
                                     if r["topology"] == topology and r[metric] is not None])
    if mean is None:
        return
    ax.axhline(mean, color=color, linestyle="--", linewidth=1.2, label=topology)
    if low is not None:
        ax.axhspan(low, high, color=color, alpha=0.08, linewidth=0)


def topology_figures(rows, config, folder):
    topologies = config["topologies"]
    colors = colors_for(topologies)
    maps = config["maps"]
    n = config["n_agents"][0]

    fig, axes = plt.subplots(2, len(maps), figsize=(4.4 * len(maps), 7.6), squeeze=False)
    for col, map_name in enumerate(maps):
        group = select_map(rows, map_name)
        swept = sorted({r["parameter"] for r in group if r["family"] == "range"
                        and not math.isinf(r["parameter"])})
        for row_index, metric in enumerate(("ISR", "rho_reach_mean")):
            ax = axes[row_index][col]
            scale = scale_of(metric)
            family_curve(ax, group, "range", "parameter", metric, RANGE_COLOR, "range r", scale)
            for reference in ("global", "none"):
                reference_band(ax, group, reference, metric, colors[reference], scale)
            log2_axis(ax, swept)
            ax.set_xlabel("communication range r (cells)")
            if col == 0:
                ax.set_ylabel(SUCCESS_LABELS["ISR"] if metric == "ISR" else REACH_LABEL)
            if metric == "ISR":
                ax.set_ylim(0, 102)
                ax.set_title(map_name)
    bottom_legend(fig, axes[0][0], 3)
    fig.suptitle(f"How far must messages carry? ({n} robots)")
    save(fig, folder, "1_success_vs_communication_range.png", 0.05)

    fig, axes = plt.subplots(1, len(maps), figsize=(4.4 * len(maps), 4.4), sharey=True,
                             squeeze=False)
    for ax, map_name in zip(axes[0], maps):
        group = select_map(rows, map_name)
        family_curve(ax, group, "range", "mean_degree", "ISR", RANGE_COLOR, "range r", 100)
        family_curve(ax, group, "knn", "mean_degree", "ISR", KNN_COLOR, "k-NN", 100, "D")
        for reference in ("global", "none"):
            reference_band(ax, group, reference, "ISR", colors[reference], 100)
        ax.set_xscale("log", base=2)
        ax.xaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter("%g"))
        ax.minorticks_off()
        ax.set_xlabel("mean links per robot (log)")
        ax.set_ylim(0, 102)
        ax.set_title(map_name)
    axes[0][0].set_ylabel(SUCCESS_LABELS["ISR"])
    bottom_legend(fig, axes[0][0], 4)
    fig.suptitle(f"Same number of links: does range or k-NN do better? ({n} robots)")
    save(fig, folder, "2_range_vs_knn_at_equal_degree.png", 0.08)

    fig, axes = plt.subplots(1, len(maps), figsize=(4.4 * len(maps), 4.4), sharey=True,
                             squeeze=False)
    for ax, map_name in zip(axes[0], maps):
        group = select_map(rows, map_name)
        for family, color, marker, label in (("range", RANGE_COLOR, "o", "range r"),
                                             ("knn", KNN_COLOR, "D", "k-NN")):
            points = family_curve(ax, group, family, "messages_per_agent_per_step", "ISR",
                                  color, label, 100, marker)
            # Write r or k next to each point.
            for x, y, _, _, parameter in points:
                ax.annotate(str(int(parameter)), (x, y), textcoords="offset points",
                            xytext=(4, -10 if family == "knn" else 5), fontsize=7, color=color)
        for topology in ("none", "global"):
            runs = [r for r in group if r["topology"] == topology]
            if runs:
                x = mean_ci([r["messages_per_agent_per_step"] for r in runs])[0]
                s = stat(runs, "ISR", 100)
                ax.errorbar([x], [s[0]], yerr=[[s[1]], [s[2]]], fmt="s", color=colors[topology],
                            label=topology, **ERROR_STYLE)
        ax.set_xscale("symlog", linthresh=0.1)
        ax.set_xlabel("delivered messages per robot per step (symlog)")
        ax.set_ylim(0, 102)
        ax.set_title(map_name)
    axes[0][0].set_ylabel(SUCCESS_LABELS["ISR"])
    bottom_legend(fig, axes[0][0], 4)
    fig.suptitle(f"More messages, more success? ({n} robots; numbers = r or k)")
    save(fig, folder, "3_messages_vs_success.png", 0.08)

    fig, axes = plt.subplots(1, len(maps), figsize=(4.4 * len(maps), 4.2), sharey=True,
                             squeeze=False)
    for ax, map_name in zip(axes[0], maps):
        group = [r for r in select_map(rows, map_name) if r["n_conflicts"]]
        range_points = family_curve(ax, group, "range", "parameter", "heard_share",
                                    RANGE_COLOR, "range r", 100)
        knn_points = family_curve(ax, group, "knn", "parameter", "heard_share",
                                  KNN_COLOR, "k-NN k", 100, "D")
        reference_band(ax, group, "global", "heard_share", colors["global"], 100)
        ticks = sorted({p[0] for p in range_points + knn_points})
        log2_axis(ax, ticks)
        ax.set_ylim(0, 108)
        ax.set_xlabel("r (range) or k (k-NN)")
        ax.set_title(map_name)
    axes[0][0].set_ylabel("Conflicts where the blocker was heard (%)")
    bottom_legend(fig, axes[0][0], 3)
    fig.suptitle(f"Was the blocking robot heard? (r ≥ 2 always hears: a blocker is "
                 f"at most 2 cells away; {n} robots)")
    save(fig, folder, "4_was_the_blocker_heard.png", 0.08)

    response_figure(rows, featured(topologies), folder, n)
    stall_figure(rows, maps, featured(topologies), folder, n)


def response_figure(rows, topologies, folder, n):
    """What happened to every conflict, pooled over maps and instances (descriptive)."""
    groups = (
        ("heard → waited", RESPONSE_COLORS["wait"], ["n_wait_heard"]),
        ("heard → stepped aside", RESPONSE_COLORS["detour"],
         ["n_detour_heard", "n_retreat_heard", "n_proceed_heard"]),
        ("not heard → waited or stepped aside", QUIET_GREY,
         ["n_wait_unheard", "n_detour_unheard", "n_retreat_unheard"]),
        ("not heard → pushed into the cell", RESPONSE_COLORS["proceed"], ["n_proceed_unheard"]),
    )
    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    totals = [sum(r[k] for r in ok_rows(rows) if r["topology"] == t
                  for _, _, keys in groups for k in keys) for t in topologies]
    bottoms = [0.0] * len(topologies)
    for label, color, keys in groups:
        shares = [100 * sum(r[k] for r in ok_rows(rows) if r["topology"] == t for k in keys)
                  / total if total else 0 for t, total in zip(topologies, totals)]
        ax.bar(topologies, shares, 0.7, bottom=bottoms, color=color, label=label)
        bottoms = [b + s for b, s in zip(bottoms, shares)]
    ax.set_ylabel("Share of conflicts (%)")
    ax.set_ylim(0, 100)
    ax.tick_params(axis="x", length=0)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2)
    ax.set_title(f"What a robot did when its next cell was blocked ({n} robots, all maps)")
    save(fig, folder, "5_how_robots_respond_to_conflicts.png")


def stall_figure(rows, maps, topologies, folder, n):
    fig, axes = plt.subplots(1, len(maps), figsize=(4.6 * len(maps), 4.4), sharey=True,
                             squeeze=False)
    causes = (("n_epistemic", "blocker not heard", RESPONSE_COLORS["proceed"]),
              ("n_rule_failure", "heard, still stuck", RESPONSE_COLORS["wait"]),
              ("n_unattributed", "no blocker identified", QUIET_GREY))
    for ax, map_name in zip(axes[0], maps):
        group = select_map(rows, map_name)
        bottoms = [0.0] * len(topologies)
        for key, label, color in causes:
            heights = [mean_ci([r[key] for r in group if r["topology"] == t])[0] or 0
                       for t in topologies]
            ax.bar(topologies, heights, 0.7, bottom=bottoms, color=color, label=label)
            bottoms = [b + h for b, h in zip(bottoms, heights)]
        ax.set_title(map_name)
        ax.tick_params(axis="x", rotation=45, length=0)
    axes[0][0].set_ylabel("Stuck robots per instance")
    bottom_legend(fig, axes[0][0], 3)
    fig.suptitle(f"Why robots got stuck ({n} robots; stuck = no progress for 10 steps)")
    save(fig, folder, "6_why_robots_got_stuck.png", 0.07)


# ------------------------------------------------------------------ scaling (E4)

def scaling_figures(rows, config, folder):
    topologies = config["topologies"]
    colors = colors_for(topologies)
    maps = config["maps"]
    sizes = dict(zip(config["n_agents"], config["size"]))
    fixed = len(set(config["size"])) == 1
    setting = (f"fixed {config['size'][0]} × {config['size'][0]} map" if fixed
               else "map grows with N, ≈ 0.03 robots per cell")

    def lines(ax, group, metric, scale=1.0):
        for j, topology in enumerate(topologies):
            # Small horizontal offsets and distinct markers keep equal series visible.
            shift = 1.04 ** (j - (len(topologies) - 1) / 2)
            ns, stats = [], []
            for n in config["n_agents"]:
                s = stat([r for r in group if r["topology"] == topology and r["n_agents"] == n],
                         metric, scale)
                if s is not None:
                    ns.append(n * shift)
                    stats.append(s)
            line(ax, ns, stats, colors[topology], "osD^v"[j % 5], topology)
        log2_axis(ax, config["n_agents"])
        if not fixed:
            ax.set_xticks(config["n_agents"], [f"{n}\n{sizes[n]}²" for n in config["n_agents"]])
        ax.set_xlabel("number of robots" + ("" if fixed else " (map size)"))

    def grid(panels, title, name):
        fig, axes = plt.subplots(len(panels), len(maps), figsize=(4.8 * len(maps), 3.9 * len(panels)),
                                 squeeze=False)
        for row_index, (metric, label, scale, limits) in enumerate(panels):
            for col, map_name in enumerate(maps):
                ax = axes[row_index][col]
                lines(ax, select_map(rows, map_name), metric, scale)
        bottom_legend(fig, axes[0][0], len(topologies))
        fig.suptitle(f"{title} ({setting})")
        save(fig, folder, name, 0.05)

    grid([("ISR", SUCCESS_LABELS["ISR"], 100, (0, 105)),
          ("CSR", SUCCESS_LABELS["CSR"], 100, (0, 105))],
         "Effect of fleet size on success", "1_success_as_fleet_grows.png")
    grid([("rho_reach_mean", REACH_LABEL, 1, None),
          ("delay_mean", "Delay of arrived robots (timesteps)", 1, None)],
         "How far stuck robots stop, and how long arrivals wait",
         "2_robustness_and_delay_as_fleet_grows.png")

    fig, axes = plt.subplots(1, len(maps), figsize=(4.8 * len(maps), 4.2), squeeze=False)
    for ax, map_name in zip(axes[0], maps):
        lines(ax, select_map(rows, map_name), "messages_per_agent_per_step")
        ax.set_yscale("symlog", linthresh=0.1)
        ax.set_ylim(bottom=0)
        ax.set_title(map_name)
    axes[0][0].set_ylabel("Messages per robot per step (symlog)")
    bottom_legend(fig, axes[0][0], len(topologies))
    fig.suptitle(f"Message load as the fleet grows ({setting})")
    save(fig, folder, "3_messages_as_fleet_grows.png", 0.08)


# ------------------------------------------------------- oracle across N (E1)

def oracle_success(rows, n, topology, metric="CSR"):
    """Success per instance; a solved oracle plan brings every robot home (CSR = ISR = 1)."""
    group = [r for r in rows if r["n_agents"] == n]
    if topology == "oracle":
        # Instances the oracle never attempted are unknown, not failures.
        instances = {r["instance_id"]: r for r in group}.values()
        return [100.0 * (r["oracle_status"] == "solved") for r in instances
                if r["oracle_status"] in ("solved", "failed", "timeout")]
    return [100.0 * r[metric] for r in group if r["topology"] == topology]


def oracle_figures(rows, config, folder):
    topologies = config["topologies"]
    colors = colors_for(topologies)
    maps = config["maps"]
    ns = config["n_agents"]
    shown = ["oracle"] + topologies

    fig, axes = plt.subplots(2, len(maps), figsize=(4.6 * len(maps), 7.8), sharey=True,
                             squeeze=False)
    for row_index, metric in enumerate(("ISR", "CSR")):
        for col, map_name in enumerate(maps):
            ax = axes[row_index][col]
            group = select_map(rows, map_name)
            for j, topology in enumerate(shown):
                shift = 1.04 ** (j - (len(shown) - 1) / 2)
                xs, stats = [], []
                for n in ns:
                    mean, low, high, _, _ = mean_ci(oracle_success(group, n, topology, metric))
                    if mean is not None:
                        xs.append(n * shift)
                        stats.append((mean, mean - (low if low is not None else mean),
                                      (high if high is not None else mean) - mean))
                line(ax, xs, stats, colors[topology], "osD^v"[j % 5],
                     "oracle (LaCAM3)" if topology == "oracle" else topology)
            log2_axis(ax, ns)
            ax.set_ylim(0, 105)
            ax.set_xlabel("number of robots")
            if col == 0:
                ax.set_ylabel(SUCCESS_LABELS[metric])
            if row_index == 0:
                ax.set_title(map_name)
    bottom_legend(fig, axes[0][0], len(shown))
    fig.suptitle(f"How close to the centralized planner? ({config['size'][0]} × "
                 f"{config['size'][0]} maps)")
    save(fig, folder, "1_success_ours_vs_oracle.png", 0.05)

    fig, axes = plt.subplots(1, len(maps), figsize=(4.6 * len(maps), 4.4), sharey=True,
                             squeeze=False)
    for ax, map_name in zip(axes[0], maps):
        group = select_map(rows, map_name)
        for j, topology in enumerate(topologies):
            shift = 1.04 ** (j - (len(topologies) - 1) / 2)
            xs, stats, counts = [], [], []
            for n in ns:
                ratios = [r["soc_ratio"] for r in group if r["topology"] == topology
                          and r["n_agents"] == n and r["soc_ratio"] is not None]
                mean, low, high, k, _ = mean_ci(ratios)
                if mean is not None:
                    xs.append(n * shift)
                    stats.append((mean, mean - (low if low is not None else mean),
                                  (high if high is not None else mean) - mean))
                    counts.append(k)
            line(ax, xs, stats, colors[topology], "osD^v"[(j + 1) % 5], topology)
            # The ratio exists only for solved instances; show how many that was.
            for x, s, k in zip(xs, stats, counts):
                ax.annotate(str(k), (x, s[0] + s[2]), textcoords="offset points", xytext=(0, 3),
                            ha="center", fontsize=7, color=colors[topology])
        ax.axhline(1, color=colors["oracle"], linestyle="--", linewidth=1.2, label="LaCAM3 = 1")
        log2_axis(ax, ns)
        ax.set_xlabel("number of robots")
        ax.set_title(map_name)
    axes[0][0].set_ylabel("SoC ÷ LaCAM3 SoC, same instance")
    bottom_legend(fig, axes[0][0], len(topologies) + 1)
    fig.suptitle("Extra cost over the centralized plan (small numbers = instances solved)")
    save(fig, folder, "2_cost_compared_with_oracle.png", 0.08)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", type=Path, help="sweep output folder with results.csv")
    args = parser.parse_args()

    apply()
    config = load_config(args.folder / "config.yaml")
    rows = load_results(args.folder)
    for row in rows:
        if row["outcome"] != "error":
            row["heard_share"] = row["n_heard"] / row["n_conflicts"] if row["n_conflicts"] else None
    folder = args.folder / "figures"
    folder.mkdir(exist_ok=True)
    {"ladder": ladder_figures, "topology": topology_figures, "scaling": scaling_figures,
     "oracle": oracle_figures}[config["kind"]](rows, config, folder)


if __name__ == "__main__":
    main()
