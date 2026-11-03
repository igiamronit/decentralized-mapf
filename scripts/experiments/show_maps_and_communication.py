"""Draw the three map types and who can hear whom under each communication setting.

python scripts/experiments/show_maps_and_communication.py --n-agents 30 --seed 1

Figure 1 shows one real instance per map type: walls, starts and goals, exactly
as the experiments use them. Figure 2 takes one instance and draws the talk
graph at the start under each setting, using the project's own topology code.
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

from figure_style import GOAL_COLOR, SETTING_COLORS, START_COLOR, apply  # noqa: E402
from decentralized_mapf.harness import MAP_TYPES, make_instance, make_topology  # noqa: E402

WALL_COLORS = matplotlib.colors.ListedColormap(["#FFFFFF", "#6E6E6E"])


def draw_map(ax, instance, links=None):
    ax.imshow(instance["grid"], cmap=WALL_COLORS, vmin=0, vmax=1)
    for i, j in links or []:
        (r1, c1), (r2, c2) = instance["starts"][i], instance["starts"][j]
        ax.plot([c1, c2], [r1, r2], color=SETTING_COLORS["global"], alpha=0.35, linewidth=0.9, zorder=1)
    ax.scatter([c for _, c in instance["starts"]], [r for r, _ in instance["starts"]],
               s=26, color=START_COLOR, edgecolors="white", linewidths=0.5, zorder=3,
               label="robot start")
    if links is None:
        ax.scatter([c for _, c in instance["goals"]], [r for r, _ in instance["goals"]],
                   s=26, marker="x", color=GOAL_COLOR, zorder=3, label="goal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.grid(False)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n-agents", type=int, default=30)
    parser.add_argument("--size", type=int, default=32)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--map", default="random", choices=MAP_TYPES,
                        help="map used for the communication figure")
    parser.add_argument("--topologies", nargs="+", default=["none", "range_2", "knn_2", "global"])
    parser.add_argument("--out", type=Path, default=ROOT / "outputs" / "figures")
    args = parser.parse_args()
    apply()
    args.out.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(1, len(MAP_TYPES), figsize=(4.6 * len(MAP_TYPES), 5.2))
    for ax, map_name in zip(axes, MAP_TYPES):
        instance = make_instance(map_name, args.n_agents, args.seed, args.size)
        draw_map(ax, instance)
        free = sum(not cell for row in instance["grid"] for cell in row)
        ax.set_title(f"{map_name} ({free} free cells)")
    handles, names = axes[0].get_legend_handles_labels()
    fig.legend(handles, names, loc="lower center", ncol=2, fontsize=9)
    fig.suptitle(f"The three map types, as used in the experiments "
                 f"({args.size} x {args.size}, N = {args.n_agents}, seed {args.seed})")
    fig.tight_layout(rect=(0, 0.06, 1, 0.95))
    path = args.out / "the_three_map_types.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"saved {path}")

    instance = make_instance(args.map, args.n_agents, args.seed, args.size)
    fig, axes = plt.subplots(1, len(args.topologies), figsize=(4.6 * len(args.topologies), 5))
    for ax, topology in zip(axes, args.topologies):
        model = make_topology(topology)
        edges = model.get_edges(instance["starts"])
        stats = model.graph_stats(edges)
        links = {tuple(sorted((i, j))) for i, receivers in edges.items() for j in receivers}
        draw_map(ax, instance, links)
        groups = stats["n_components"]
        ax.set_title(f"{topology}\nmean degree {stats['mean_degree']:.1f}, "
                     f"{groups} group{'s' if groups != 1 else ''}", fontsize=10)
    fig.suptitle(f"Who can hear whom at the start ({args.map} map, N = {args.n_agents}; "
                 "a line = at least one direction of a link)")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    path = args.out / "who_can_hear_whom.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"saved {path}")


if __name__ == "__main__":
    main()
