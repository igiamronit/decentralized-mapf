"""Record one episode with POGEMA's own renderer, to check runs by eye.

python scripts/experiments/animate_episode.py --map warehouse --n-agents 20 --seed 3 --topologies none global

The drawing comes from POGEMA's AnimationWrapper, not from our plotting code,
so it is an independent view of what the simulator actually did. Each topology
runs on the same instance. Saves one .mp4 per topology.

Needs: pip install imageio imageio-ffmpeg
"""

import argparse
import sys
from pathlib import Path

from pogema import AnimationWrapper

ROOT = Path(__file__).resolve().parents[2]
# Let the script run from the repository root without installing the package.
sys.path.insert(0, str(ROOT))

from decentralized_mapf import Metrics, PerfectChannel, run_episode  # noqa: E402
from decentralized_mapf.harness import build_run, make_instance  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--map", default="warehouse", choices=("random", "warehouse", "maze"))
    parser.add_argument("--n-agents", type=int, default=20)
    parser.add_argument("--size", type=int, default=32, help="map side length")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--topologies", nargs="+", default=["none", "global"])
    parser.add_argument("--max-steps", type=int, default=256)
    parser.add_argument("--out", type=Path, default=ROOT / "outputs" / "animations")
    args = parser.parse_args()

    instance = make_instance(args.map, args.n_agents, args.seed, args.size)
    args.out.mkdir(parents=True, exist_ok=True)
    for topology in args.topologies:
        env, comm, planner = build_run(instance, topology, args.max_steps)
        env = AnimationWrapper(env)
        # Animation must be switched on before the reset inside run_episode.
        env.enable_animation()
        try:
            env.reset(seed=args.seed)
            goals = env.unwrapped.get_targets_xy(ignore_borders=True)
            metrics = Metrics(goals, seed=args.seed, intent_provider=planner.intended_steps)
            summary = run_episode(env, comm, PerfectChannel(), planner, metrics, args.max_steps)
            name = f"{args.map}_{args.n_agents}_robots_seed{args.seed}_{topology}"
            env.save_video_animation(str(args.out / f"{name}.mp4"), fps=8)
        finally:
            env.close()
        print(f"{topology}: {summary['n_arrived']}/{args.n_agents} robots arrived in "
              f"{summary['steps']} steps -> {args.out / name}.mp4")


if __name__ == "__main__":
    main()
