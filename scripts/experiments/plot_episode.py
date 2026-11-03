"""Show one instance under several topologies: paths, conflicts and progress.

python scripts/experiments/plot_episode.py --map random --n-agents 20 --seed 1 --topologies global range_2 none

Top row: each robot's path; markers show how it responded to a conflict
(filled = it heard the blocker, hollow = it did not). Bottom row: each robot's
shortest-path distance to its goal over time.
"""

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
# Let the script run from the repository root without installing the package.
sys.path.insert(0, str(ROOT))

from figure_style import RESPONSE_COLORS, apply  # noqa: E402
from decentralized_mapf.coordination import goal_distances  # noqa: E402
from decentralized_mapf.harness import make_instance, run_one  # noqa: E402

RESPONSE_STYLE = {name: (RESPONSE_COLORS[name], marker) for name, marker in
                  (("wait", "o"), ("detour", "^"), ("retreat", "v"), ("proceed", "s"))}


def draw_paths(ax, instance, trace, events, title):
    ax.imshow(instance["grid"], cmap="Greys", vmin=0, vmax=1.6)
    # tab20c: blues, oranges, greens, purples and greys, no reds.
    colors = plt.get_cmap("tab20c")
    for i, goal in enumerate(instance["goals"]):
        path = [row["positions"][i] for row in trace]
        color = colors(i % 20)
        ax.plot([p[1] for p in path], [p[0] for p in path], color=color, linewidth=1.2, alpha=0.8)
        ax.scatter(path[0][1], path[0][0], color=color, s=18, zorder=3)
        ax.scatter(goal[1], goal[0], color=color, marker="x", s=22, zorder=3)
    for event in events:
        r, c = trace[event["t"]]["positions"][event["agent"]]
        color, marker = RESPONSE_STYLE[event["response"]]
        ax.scatter(c, r, marker=marker, s=28, zorder=4, edgecolors=color,
                   facecolors=color if event["heard"] else "none", linewidths=1)
    ax.set_title(title, fontsize=10)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.grid(False)


def draw_progress(ax, instance, trace):
    curves = []
    for i, goal in enumerate(instance["goals"]):
        distances = goal_distances(instance["grid"], goal)
        curve = [distances[tuple(row["positions"][i])] for row in trace]
        curves.append(curve)
        ax.plot(curve, color="gray", linewidth=0.6, alpha=0.6)
    mean_curve = [sum(c[t] for c in curves) / len(curves) for t in range(len(trace))]
    ax.plot(mean_curve, color="black", linewidth=2, label="mean")
    ax.set_title("Distance to goal over time (shortest-path cells)", fontsize=10)
    ax.set_xlabel("timestep t")
    ax.set_ylabel("distance")
    ax.legend(fontsize=8)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--map", default="random", choices=("random", "warehouse", "maze"))
    parser.add_argument("--n-agents", type=int, default=20)
    parser.add_argument("--size", type=int, default=32, help="map side length")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--topologies", nargs="+", default=["global", "range_2", "none"])
    parser.add_argument("--max-steps", type=int, default=256)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    apply()

    # One instance, so every topology sees the same map, starts and goals.
    instance = make_instance(args.map, args.n_agents, args.seed, args.size)
    fig, axes = plt.subplots(2, len(args.topologies), squeeze=False,
                             figsize=(5.5 * len(args.topologies), 10))
    for col, topology in enumerate(args.topologies):
        row, details = run_one(instance, topology, args.max_steps)
        trace, events = details["raw"]["trace"], details["conflicts"]
        title = (f"{topology} (ISR {row['ISR']:.2f}, {row['steps']} steps, "
                 f"{row['n_heard']}/{row['n_conflicts']} conflicts heard)")
        draw_paths(axes[0][col], instance, trace, events, title)
        draw_progress(axes[1][col], instance, trace)

    handles = [plt.Line2D([], [], color=color, marker=marker, linestyle="", label=response)
               for response, (color, marker) in RESPONSE_STYLE.items()]
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False,
               title="response to a conflict (filled = blocker heard, hollow = not heard)")
    fig.suptitle(f"Same instance, only communication changes · {args.map} map · "
                 f"N = {args.n_agents} · seed {args.seed}", fontsize=12)
    fig.tight_layout(rect=[0, 0.06, 1, 0.97])

    out = args.out or ROOT / "outputs" / "figures" / f"episode_{args.map}_n{args.n_agents}_s{args.seed}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    print(f"saved {out}")


if __name__ == "__main__":
    main()
