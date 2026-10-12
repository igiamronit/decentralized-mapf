from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from pogema import pogema_v0, GridConfig, AStarAgent

CFG = GridConfig(num_agents=16, size=24, density=0.3, seed=7,
                 obs_radius=3, max_episode_steps=128,
                 observation_type='POMAPF')

env = pogema_v0(grid_config=CFG)
obs, info = env.reset()
agents = [AStarAgent() for _ in range(CFG.num_agents)]

obstacles = np.array(env.unwrapped.get_obstacles(ignore_borders=False))
goals = list(env.unwrapped.grid.finishes_xy)

frames = [list(env.unwrapped.grid.positions_xy)]
for _ in range(CFG.max_episode_steps):
    actions = [a.act(o) for a, o in zip(agents, obs)]
    obs, reward, terminated, truncated, info = env.step(actions)
    frames.append(list(env.unwrapped.grid.positions_xy))
    if all(terminated) or all(truncated):
        break

FRAME = min(20, len(frames) - 1)
pos = frames[FRAME]

# agents that haven't moved for 10 steps and aren't at their goal = stuck
stuck = set()
if FRAME >= 10:
    for i, p in enumerate(pos):
        if p == frames[FRAME - 10][i] and p != goals[i]:
            stuck.add(i)

def edges(positions, radius):
    out = []
    for i in range(len(positions)):
        for j in range(i + 1, len(positions)):
            d = abs(positions[i][0] - positions[j][0]) + abs(positions[i][1] - positions[j][1])
            if d <= radius:
                out.append((i, j))
    return out

panels = [("Global communication", 10**6),
          ("Range-limited (r = 6)", 6),
          ("No communication", 0)]

fig, axes = plt.subplots(1, 3, figsize=(15, 5.4))

for ax, (title, radius) in zip(axes, panels):
    ax.imshow(obstacles, cmap='Greys', vmin=0, vmax=1.6, origin='upper')

    for i, j in edges(pos, radius):
        ax.plot([pos[i][1], pos[j][1]], [pos[i][0], pos[j][0]],
                color='tab:blue', alpha=0.35, lw=1.1, zorder=1)

    for i, (r, c) in enumerate(pos):
        ax.scatter(c, r, s=70, zorder=3,
                   color='tab:red' if i in stuck else 'tab:green',
                   edgecolors='black', linewidths=0.5)
        gr, gc = goals[i]
        ax.scatter(gc, gr, s=45, marker='x', color='dimgray', alpha=0.65, zorder=2)

    n_edges = len(edges(pos, radius))
    deg = 2 * n_edges / len(pos)
    ax.set_title(f"{title}\nedges = {n_edges}   mean degree = {deg:.1f}", fontsize=11)
    ax.set_xticks([]); ax.set_yticks([])

legend = [Line2D([], [], marker='o', ls='', color='tab:green', label='agent'),
          Line2D([], [], marker='o', ls='', color='tab:red', label='stuck agent'),
          Line2D([], [], marker='x', ls='', color='dimgray', label='goal'),
          Line2D([], [], color='tab:blue', alpha=0.5, label='communication link')]
fig.legend(handles=legend, loc='lower center', ncol=4, frameon=False)

fig.suptitle(f"Same instance, same timestep ({FRAME}) — communication topology only varies",
             fontsize=13)
fig.tight_layout(rect=[0, 0.06, 1, 0.96])
output_dir = Path(__file__).resolve().parents[2] / "outputs" / "figures"
output_dir.mkdir(parents=True, exist_ok=True)
output_path = output_dir / "comm_topology_figure.png"
fig.savefig(output_path, dpi=200)
print(f"saved {output_path}")
