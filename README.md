# Decentralized MAPF under Communication Constraints

Multi-Agent Systems course project at IIT Hyderabad. We study how communication
range, topology, and reliability affect decentralized robot coordination on a
grid, using POGEMA as the simulation environment.

The planned study keeps one decentralized planner fixed across global, none,
range-limited, and k-nearest-neighbour communication. LaCAM3 provides a separate
centralized comparison baseline.

## Current status

Ronit's environment verification, shared interfaces, global/no-communication
models, perfect channel, and episode runner are implemented. See
[environment verification results](docs/ENVIRONMENT_CHECK_RESULTS.md).

The team's planner, metrics/monitors, LaCAM3 integration, experiment harness,
and range/k-nearest models remain to be integrated. The oracle/global/none
comparison awaits those dependencies; loss/delay extensions follow core validation.

For context, read [the team build guide](docs/TEAM_BUILD_GUIDE.md) for assignments
and contracts, and [the project specification](docs/PROJECT_SPEC.md) for research
requirements. This README covers the current implementation and how to use it.

## Layout

```text
decentralized_mapf/
  interfaces.py              Shared message, trace, communication, channel, and planner contracts
  communication.py           Global/no-communication models and reusable graph statistics
  channels.py                Perfect channel; inherits the base pass-through behavior
  runner.py                  Pluggable POGEMA episode loop and per-recipient routing
  __init__.py                Public imports for project modules
tests/
  test_communication.py       Communication links and directed-graph statistics checks
  test_runner.py              Real POGEMA integration with test-only planners and channels
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

## Shared interfaces

All project modules should import the shared definitions instead of creating
their own copies. Run Python from the repository root:

```python
from decentralized_mapf import Message, StepRecord, CommunicationModel, Channel, Planner
```

`interfaces.py` contains the shared data formats and base classes. Concrete
models and planners inherit from them; the base channel is already pass-through.
Coordinate conventions, directed links, and integration contracts are documented
in [the guide's interface section](docs/TEAM_BUILD_GUIDE.md#3-frozen-interfaces--do-not-change-after-everyone-starts)
and the code docstrings.

## Communication models

Both models implement `CommunicationModel` and require no constructor settings:

```python
from decentralized_mapf import GlobalCommunication, NoCommunication

positions = [(0, 0), (0, 1), (50, 50)]
comm = GlobalCommunication()  # Swap for NoCommunication() to disable messages.
edges = comm.get_edges(positions)  # {0: [1, 2], 1: [0, 2], 2: [0, 1]}
stats = comm.graph_stats(edges)
# {'mean_degree': 2.0, 'n_components': 1, 'is_connected': True}
```

These models select potential links. Future models can reuse `graph_stats` from
`decentralized_mapf.communication`. Observation remains independent of communication.

## Perfect channel

`PerfectChannel` in `channels.py` inherits the base channel's immediate, unchanged
delivery. Future imperfect channels use the same `deliver()` and `reset()` interface.
The runner creates independent per-recipient transmissions; channels must preserve
the recipient and sending timestamp.

## Episode runner

Pass teammate implementations into one function; the runner contains no planner
algorithm, monitor, plotting code, or experiment configuration:

```python
from decentralized_mapf import GlobalCommunication, PerfectChannel, run_episode

# env, planner, and metrics are created by the calling experiment code.
result = run_episode(env, GlobalCommunication(), PerfectChannel(),
                     planner, metrics, max_steps=256)
```

Supply a seeded POMAPF environment with `on_target='finish'`, a planner inheriting
`Planner`, and a fresh recorder exposing `record()` and `summary()`. Planner
`reset()`/`observe()` hooks support episode initialization and fresh broadcasts.
The runner records initial through final states and returns the recorder's summary.
See the guide and `runner.py` for callback order, trace semantics, and finished-robot
handling. The calling experiment code owns configuration and environment cleanup.

## Validation

From the repository root with the environment activated:

```powershell
python -m unittest discover -s tests -v
```

The last code validation passed all 18 tests, covering graph statistics and real
POGEMA integration, including routing, drops/delays, reset, and stopping behavior.
Fake planners and imperfect channels exist only in tests. Robot-coordination
performance remains unvalidated until the real team modules are integrated.

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

- Read [the team build guide](docs/TEAM_BUILD_GUIDE.md),
  [project specification](docs/PROJECT_SPEC.md), and [agent instructions](AGENTS.md).
- Keep this README current with a concise implementation handoff; put detailed
  contracts in the guide and implementation assumptions in code docstrings.
- Complete the core before extensions and preserve the frozen module interfaces.
- Seed experiments, compare matched instances, and save raw results and traces
  before aggregation. Evaluate formal-methods monitors offline.
- Keep generated output and local environments out of Git.
- Make commits only when Ronit explicitly requests them. Never add AI coauthors.
