# Decentralized MAPF under Communication Constraints

Multi-Agent Systems course project at IIT Hyderabad. We study how communication range, topology, and reliability affect decentralized robot coordination on a grid, using POGEMA as the simulation environment.

The planned study keeps one decentralized planner fixed across global, none, range-limited, and k-nearest-neighbour communication. LaCAM3 provides a separate centralized comparison baseline.

## Current status

Environment verification, shared interfaces, all four core communication models (global, none, range, k-nearest), the perfect channel, episode runner, and planners are implemented. See [environment verification results](docs/ENVIRONMENT_CHECK_RESULTS.md).

The C6 centralized LaCAM3 oracle adapter, oracle path validation, and oracle metrics are implemented and tested. The oracle runs independently of the decentralized simulation loop and provides a centralized reference for evaluation.

The broader offline metrics/monitors and experiment harness remain to be integrated. The oracle/global/none comparison and topology sweeps, matched-degree calibration, and experimental results are still pending. Loss/delay extensions follow core validation.

For context, read [the team build guide](docs/TEAM_BUILD_GUIDE.md) for assignments and contracts, and [the project specification](docs/PROJECT_SPEC.md) for research requirements. This README covers the current implementation and how to use it.

## Layout

```text
decentralized_mapf/
  interfaces.py              Shared message, trace, communication, channel, and planner contracts
  communication.py           Global, none, range, k-nearest models and shared graph statistics
  channels.py                 Perfect channel; inherits the base pass-through behavior
  runner.py                   Pluggable POGEMA episode loop and per-recipient routing
  pathfinding.py               Shared deterministic static-map A*
  planner.py                   IndependentAStar and DCMAPFPlanner with local yielding
  oracle/
    __init__.py                Public oracle exports
    lacam_adapter.py           LaCAM3 executable adapter and MovingAI conversion
    validation.py              MAPF problem and solution validation
    metrics.py                 Makespan, SoC, and oracle SoC ratio
  __init__.py                  Public imports for project modules

tests/
  test_communication.py        Communication links and directed-graph statistics checks
  test_topologies.py           Range/k-nearest behavior, limits, and deterministic tie-breaking
  test_runner.py                Real POGEMA integration with test-only planners and channels
  test_planner.py               Pathfinding, broadcasts and local yield decisions
  test_planner_integration.py   Planner episodes, retreat, waiting and reset
  test_lacam_adapter.py         LaCAM3 adapter, parser, timeout and failure handling
  test_oracle_metrics.py        Oracle metric calculations
  test_oracle_validation.py     Problem and solution validation

docs/
  TEAM_BUILD_GUIDE.md           Team assignments, frozen interfaces, implementation guide
  PROJECT_SPEC.md               Research question, experiment plan, references
  MAS_Project_Proposal.pdf      Project proposal
  ENVIRONMENT_CHECK_RESULTS.md  Verified C1 checklist, evidence, and API findings
  figures/                      Preserved proposal and explanatory figures

scripts/
  checks/
    verify_environment.py       Six independently callable C1 environment checks
  demos/
    astar_animation.py          Independent A* demonstration and animation export
    topology_snapshot.py        Communication-graph illustration on one A* trajectory

outputs/                         Generated artifacts (ignored by Git)
mapf-env/                        Existing local virtual environment (ignored by Git)
requirements.txt                 Direct dependencies, including the installed POGEMA revision
AGENTS.md                        Repository instructions for coding assistants
```

The topology snapshot overlays different communication graphs on the same trajectory; it does not yet measure communication's effect on movement. The expected-results figure contains illustrative hypotheses, not experimental data.

## Setup

The project uses Python 3.13. From the repository root in PowerShell:

```powershell
# Reuse the existing environment:
.\mapf-env\Scripts\Activate.ps1

# Or create a new environment:
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Use one of the environment options above. Installing the pinned POGEMA revision requires Git. The requirements record the existing direct dependency versions; they are not a complete lockfile of transitive dependencies.

## Shared interfaces

All project modules should import the shared definitions instead of creating their own copies. Run Python from the repository root:

```python
from decentralized_mapf import Message, StepRecord, CommunicationModel, Channel, Planner
```

`interfaces.py` contains the shared data formats and base classes. Concrete models and planners inherit from them; the base channel is already pass-through. Coordinate conventions, directed links, and integration contracts are documented in [the guide's interface section](docs/TEAM_BUILD_GUIDE.md#3-frozen-interfaces--do-not-change-after-everyone-starts) and the code docstrings.

## Communication models

All four models implement `CommunicationModel` and are importable from the package:

```python
from decentralized_mapf import (
    GlobalCommunication, NoCommunication, RangeCommunication, KNNCommunication,
)

positions = [(0, 0), (0, 1), (50, 50)]
comm = GlobalCommunication()  # Swap for NoCommunication() to disable messages.
# Or use RangeCommunication(r=3) / KNNCommunication(k=2).
edges = comm.get_edges(positions)
stats = comm.graph_stats(edges)
```

Range uses inclusive Manhattan distance `<= r`; k-NN sends to up to `k` nearest robots by Manhattan distance, with ties resolved by robot ID. k-NN links are directed. Both reuse `graph_stats` in `decentralized_mapf.communication`.

The runner selects neighbours among active robots before mapping links back to their original IDs, so finished robots do not consume k-NN slots. Observation remains independent of communication.

## Perfect channel

`PerfectChannel` in `channels.py` inherits the base channel's immediate, unchanged delivery. Future imperfect channels use the same `deliver()` and `reset()` interface. The runner creates independent per-recipient transmissions; channels must preserve the recipient and sending timestamp.

## Episode runner

Pass teammate implementations into one function; the runner contains no planner algorithm, monitor, plotting code, or experiment configuration:

```python
from decentralized_mapf import GlobalCommunication, PerfectChannel, run_episode

# env, planner, and metrics are created by the calling experiment code.
result = run_episode(
    env, GlobalCommunication(), PerfectChannel(),
    planner, metrics, max_steps=256
)
```

Supply a seeded POMAPF environment with `on_target='finish'`, a planner inheriting `Planner`, and a fresh recorder exposing `record()` and `summary()`. Planner `reset()`/`observe()` hooks support episode initialization and fresh broadcasts. The runner records initial through final states and returns the recorder's summary.

See the guide and `runner.py` for callback order, trace semantics, and finished-robot handling. The calling experiment code owns configuration and environment cleanup.

## Planner

`IndependentAStar` follows a shortest static-map path and ignores messages. `DCMAPFPlanner` uses the same pathfinding helper and resolves local conflicts from its inbox: lower IDs win cell contention, while a lower-priority robot attempts a detour or a retreat into a side pocket on a head-on swap. Both assume prior knowledge of the static obstacle map and use map-relative row/column coordinates.

```python
from decentralized_mapf import DCMAPFPlanner

planner = DCMAPFPlanner(grid_map=[[0, 0, 0]], goals=[(0, 2)])
planner.observe(0, observation={}, position=(0, 0), goal=(0, 2))
message = planner.compose(0, t=0)
action = planner.act(0, observation={}, inbox=[], goal=(0, 2))
```

For an episode, pass the planner to `run_episode` with the chosen communication model, channel and a compatible recorder. Supply `moves=config.MOVES` if the POGEMA action ordering is customized. The runner calls `observe()` before every broadcast; paths advance only after the next observed position confirms a move.

No communication gives independent A* behavior without changing planners. When yielding, a robot can retreat along a corridor to reach an off-axis pocket. It keeps that refuge until its goal route is clear or the peer is no longer heard. Only received positions and claims constrain the escape search.

This is a simplified A* plus local yield baseline, not a validated reproduction of the full published algorithm or a complete MAPF solver. Narrow bottlenecks and multi-robot cycles may still stall. See the [planner contract](docs/TEAM_BUILD_GUIDE.md#planner) for the exact rule.

## Centralized LaCAM3 oracle (C6)

The oracle provides a centralized reference solution for a MAPF instance. It is intended for evaluation and comparison; it is **not called by `run_episode()` and must not be inserted into the decentralized planner or communication loop**.

The implementation is in `decentralized_mapf/oracle/`:

- `lacam_adapter.py` converts the grid and start/goal configuration into MovingAI map/scenario files, invokes the LaCAM3 executable, and parses its solution.
- `validation.py` validates the input problem and returned paths, including coordinate validity, obstacle avoidance, legal transitions, vertex collisions, and edge swaps.
- `metrics.py` calculates makespan, sum of costs (SoC), and the decentralized-to-oracle SoC ratio.

### LaCAM3 executable setup on Windows

The LaCAM3 executable and its required runtime DLLs are external dependencies. Keep them together in a local runtime directory; do not add executable or DLL files to the project repository.

For example, if the runtime files are in `C:\Users\<username>\Downloads\lacam3-runtime\`, set the executable path in the PowerShell terminal before running the oracle:

```powershell
$env:LACAM3_BINARY_PATH = "$HOME\Downloads\lacam3-runtime\main.exe"
Test-Path $env:LACAM3_BINARY_PATH
```

The final command should return `True`. The adapter checks `LACAM3_BINARY_PATH` first and also checks its configured project-local candidate paths.

The environment variable is scoped to the current PowerShell session. Set it again in a new terminal session before invoking the oracle.

### Oracle usage

Run from the repository root with the project environment activated:

```python
from decentralized_mapf.oracle import (
    oracle_solve,
    oracle_metrics,
    oracle_soc_ratio,
)

grid = [
    [0, 0, 0],
    [0, 0, 0],
    [0, 0, 0],
]
starts = [(0, 0), (2, 2)]
goals = [(2, 2), (0, 0)]

paths = oracle_solve(grid, starts, goals, timeout=30)

if paths is not None:
    reference = oracle_metrics(paths)
    print("Oracle paths:", paths)
    print("Oracle metrics:", reference)
```

The grid uses `0` for free cells and `1` for obstacles. Coordinates are `(row, column)`. The adapter validates the problem and returned paths. If the executable is unavailable, the solver fails, or the call times out, `oracle_solve()` returns `None`; callers should check this before calculating metrics.

The returned paths use the transition-based convention: the initial position is included, and each subsequent position represents one timestep transition.

### Oracle metrics

```python
from decentralized_mapf.oracle import oracle_metrics, oracle_soc_ratio

reference = oracle_metrics(paths)

# Compare a decentralized run's SoC against the oracle's SoC:
ratio = oracle_soc_ratio(decentralized_soc, reference["SoC"])
```

`oracle_metrics()` returns a dictionary containing `makespan` and `SoC`. Under the transition-based convention, each agent's cost is the number of transitions in its path (`len(path) - 1`). Makespan is the maximum individual path cost; SoC is the sum of individual path costs.

`oracle_soc_ratio()` computes decentralized SoC divided by oracle SoC. A value of `1.0` means equal SoC; values above `1.0` indicate higher decentralized cost. A zero oracle SoC is rejected because the ratio is undefined.

The oracle is a centralized comparison reference, not evidence that the decentralized planner is optimal or complete. Oracle metrics do not replace the broader experiment recorder, offline monitors, or statistical analysis.

## Validation

From the repository root with the Python 3.13 environment activated:

```powershell
python -m pytest -q -p no:cacheprovider
```

The current integrated test suite passes **103 tests and 55 subtests**. It includes communication and runner checks, planner unit and integration tests using real POGEMA, and the C6 oracle metrics, validation, and adapter tests.

The C6 tests cover malformed inputs and paths, coordinate conversion, collision and transition validation, metric calculations, parser failure cases, invalid timeouts, and adapter failure handling. A separate smoke test has also successfully invoked the actual Windows LaCAM3 executable and returned valid paths with makespan 4 and SoC 8 for a two-agent 3×3 test instance.

These are implementation and correctness checks, not experimental performance results.

## Run the existing scripts

With an environment activated, run these commands from the repository root:

```powershell
python scripts/checks/verify_environment.py
python scripts/demos/astar_animation.py
python scripts/demos/topology_snapshot.py
```

The verifier replaces the old smoke-test and collision scripts. It runs all six C1 checks, prints PASS/FAIL, writes raw evidence to `outputs/verification/environment.json`, and exits nonzero if any check fails. Use `--seed 42` to change its seed or `--output <path>` to save another result. The verifier's 100-agent timing uses random actions, not `DCMAPFPlanner`.

The animation demo writes `outputs/renders/demo.svg` and `outputs/renders/demo.html`. The topology demo writes `outputs/figures/comm_topology_figure.png`. Scripts create their output directories automatically; the preserved figures in `docs/figures/` are not overwritten.

## Working agreements

- Read [the team build guide](docs/TEAM_BUILD_GUIDE.md), [project specification](docs/PROJECT_SPEC.md), and [agent instructions](AGENTS.md).
- Keep this README current with a concise implementation handoff; put detailed contracts in the guide and implementation assumptions in code docstrings.
- Complete the core before extensions and preserve the frozen module interfaces.
- Seed experiments, compare matched instances, and save raw results and traces before aggregation. Evaluate formal-methods monitors offline.
- Keep generated output and local environments out of Git.
- Make commits only when the user explicitly requests them. Never add AI coauthors.