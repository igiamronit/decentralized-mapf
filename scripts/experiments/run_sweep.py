"""Run one experiment config and save its results under outputs/experiments/."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Let the script run from the repository root without installing the package.
sys.path.insert(0, str(ROOT))

from decentralized_mapf.harness import load_config, run_sweep  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path, help="experiment YAML, e.g. experiments/ladder.yaml")
    parser.add_argument("--out", type=Path, help="output folder (default: outputs/experiments/<name>)")
    parser.add_argument("--workers", type=int, default=1, help="parallel processes")
    args = parser.parse_args()

    out = args.out or ROOT / "outputs" / "experiments" / load_config(args.config)["name"]
    rows = run_sweep(args.config, out, workers=args.workers)
    print(f"Saved {len(rows)} runs to {out / 'results.csv'}")


if __name__ == "__main__":
    main()
