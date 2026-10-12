# Decentralized MAPF under Communication Constraints

Multi-Agent Systems course project at IIT Hyderabad. We study how communication
range, topology, and reliability affect decentralized robot coordination on a
grid, using POGEMA as the simulation environment.

The planned study keeps one decentralized planner fixed across global, none,
range-limited, and k-nearest-neighbour communication. LaCAM3 provides a separate
centralized comparison baseline.

## Current status

This repository currently contains the project proposal, specification, team
build guide, a modular POGEMA environment verifier, and demonstrations. The communication
layer, integrated planner, monitoring suite, oracle integration, and experiment
harness have not yet been implemented here. C1 environment verification is
complete; see [the recorded results](docs/ENVIRONMENT_CHECK_RESULTS.md).

## Layout

```text
docs/
  TEAM_BUILD_GUIDE.md          Team assignments, frozen interfaces, implementation guide
  PROJECT_SPEC.md              Research question, experiment plan, references
  MAS_Project_Proposal.pdf     Project proposal
  ENVIRONMENT_CHECK_RESULTS.md Verified C1 checklist, evidence, and API findings
  figures/                    Preserved proposal and explanatory figures
scripts/
  checks/
    verify_environment.py     Six independently callable C1 environment checks
  demos/
    astar_animation.py        Independent A* demonstration and animation export
    topology_snapshot.py      Communication-graph illustration on one A* trajectory
outputs/                      Generated artifacts (ignored by Git)
mapf-env/                     Existing local virtual environment (ignored by Git)
requirements.txt              Direct dependencies, including the installed POGEMA revision
AGENTS.md                     Repository instructions for coding assistants
```

The topology snapshot overlays different communication graphs on the same
trajectory; it does not yet measure communication's effect on movement. The
expected-results figure contains illustrative hypotheses, not experimental data.

## Setup

The existing environment uses Python 3.13. From the repository root in PowerShell:

```powershell
# Reuse the existing environment:
.\mapf-env\Scripts\Activate.ps1

# Or create a new environment:
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Use one of the environment options above. Installing the pinned POGEMA revision
requires Git. The requirements record the existing direct dependency versions;
they are not a complete lockfile of transitive dependencies.

## Run the existing scripts

With an environment activated, run these commands from the repository root:

```powershell
python scripts/checks/verify_environment.py
python scripts/demos/astar_animation.py
python scripts/demos/topology_snapshot.py
```

The verifier replaces the old smoke-test and collision scripts. It runs all six
C1 checks, prints PASS/FAIL, writes raw evidence to
`outputs/verification/environment.json`, and exits nonzero if any check fails.
Use `--seed 42` to change its seed or `--output <path>` to save another result.
The 100-agent timing uses random actions, not the future decentralized planner.

The animation demo writes `outputs/renders/demo.svg` and
`outputs/renders/demo.html`. The topology demo writes
`outputs/figures/comm_topology_figure.png`. Scripts create their output directories
automatically; the preserved figures in `docs/figures/` are not overwritten.

## Working agreements

- Start with [the team build guide](docs/TEAM_BUILD_GUIDE.md).
- Complete the core before extensions and preserve the frozen module interfaces.
- Seed experiments, compare matched instances, and save raw results and traces
  before aggregation. Evaluate formal-methods monitors offline.
- Keep generated output and local environments out of Git.
- Make commits only when Ronit explicitly requests them. Never add AI coauthors.
