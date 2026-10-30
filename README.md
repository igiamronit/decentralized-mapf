# Decentralized MAPF under Communication Constraints

Multi-Agent Systems course project at IIT Hyderabad. We study how communication
range, topology, and reliability affect decentralized robot coordination on a
grid, using POGEMA as the simulation environment.

The planned study keeps one decentralized planner fixed across global, none,
range-limited, and k-nearest-neighbour communication. LaCAM3 provides a separate
centralized comparison baseline.

## Current status

Environment verification, shared interfaces, all four core communication models
(global, none, range, k-nearest), the perfect channel, episode runner, planners,
and metrics/monitors are implemented. See
[environment verification results](docs/ENVIRONMENT_CHECK_RESULTS.md).

LaCAM3 integration and the experiment harness remain pending. The
oracle/global/none comparison and topology sweeps
await those dependencies; matched-degree calibration and experimental results
are still pending. Loss/delay extensions follow core validation.

For context, read [the team build guide](docs/TEAM_BUILD_GUIDE.md) for assignments
and contracts, and [the project specification](docs/PROJECT_SPEC.md) for research
requirements. This README covers the current implementation and how to use it.

## Layout

```text
decentralized_mapf/
  interfaces.py              Shared message, trace, communication, channel, and planner contracts
  communication.py           Global, none, range, k-nearest models and shared graph statistics
  channels.py                Perfect channel; inherits the base pass-through behavior
  runner.py                  Pluggable POGEMA episode loop and per-recipient routing
  pathfinding.py             Shared deterministic static-map A*
  planner.py                 IndependentAStar and DCMAPFPlanner with local yielding
  metrics.py                 Trace recorder, POGEMA metric capture, raw bundle export
  monitors.py                Offline reachability, liveness, safety and stall diagnosis
  __init__.py                Public imports for project modules
tests/
  test_communication.py       Communication links and directed-graph statistics checks
  test_topologies.py          Range/k-nearest behavior, limits, and deterministic tie-breaking
  test_runner.py              Real POGEMA integration with test-only planners and channels
  test_planner.py             Pathfinding, broadcasts and local yield decisions
  test_planner_integration.py Planner episodes, retreat, waiting and reset
  test_metrics.py             Analytic monitor traces and JSON persistence
  test_episode_integration.py Real POGEMA episodes with planner and metrics modules
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

All four models implement `CommunicationModel` and are importable from the package:

```python
from decentralized_mapf import (
    GlobalCommunication, NoCommunication, RangeCommunication, KNNCommunication,
)

positions = [(0, 0), (0, 1), (50, 50)]
comm = GlobalCommunication()  # Swap for NoCommunication() to disable messages.
# Or use RangeCommunication(r=3) / KNNCommunication(k=2).
edges = comm.get_edges(positions)  # {0: [1, 2], 1: [0, 2], 2: [0, 1]}
stats = comm.graph_stats(edges)
# {'mean_degree': 2.0, 'n_components': 1, 'is_connected': True}
```

Range uses inclusive Manhattan distance `<= r`; k-NN sends to up to `k` nearest
robots by Manhattan distance, with ties resolved by robot ID. k-NN links are
directed. Both reuse `graph_stats` in `decentralized_mapf.communication`.
The runner selects neighbours among active robots before mapping links back to
their original IDs, so finished robots do not consume k-NN slots. Observation
remains independent of communication.

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

## Planner

`IndependentAStar` follows a shortest static-map path and ignores messages.
`DCMAPFPlanner` uses the same pathfinding helper and resolves local conflicts from
its inbox: lower IDs win cell contention, while a lower-priority robot attempts a
detour or a retreat into a side pocket on a head-on swap. Both assume prior knowledge of the
static obstacle map and use map-relative row/column coordinates.

```python
from decentralized_mapf import DCMAPFPlanner

planner = DCMAPFPlanner(grid_map=[[0, 0, 0]], goals=[(0, 2)])
planner.observe(0, observation={}, position=(0, 0), goal=(0, 2))
message = planner.compose(0, t=0)
action = planner.act(0, observation={}, inbox=[], goal=(0, 2))
```

For an episode, pass the planner to `run_episode` with the chosen communication
model, channel and a compatible recorder. Supply `moves=config.MOVES` if the
POGEMA action ordering is customized. The runner calls `observe()` before every
broadcast; paths advance only after the next observed position confirms a move.
No communication gives independent A* behavior without changing planners.
When yielding, a robot can retreat along a corridor to reach an off-axis
pocket. It keeps that refuge until its goal route is clear or the peer is no
longer heard. Only received positions and claims constrain the escape search.

This is a simplified A* plus local yield baseline, not a validated reproduction
of the full published algorithm or a complete MAPF solver. Narrow bottlenecks
and multi-robot cycles may still stall. The centralized oracle, experiment
harness and statistical comparisons remain integration dependencies.
See the [planner contract](docs/TEAM_BUILD_GUIDE.md#planner) for the exact rule.

## Metrics and monitors

The planner and metrics modules work through the shared runner. This small deterministic
fixture exercises a head-on conflict with room for a detour; it is a correctness
example, not an experimental comparison:

```python
import json
from pathlib import Path
from pogema import GridConfig, SumOfCostsAndMakespanMetric, pogema_v0
from decentralized_mapf import DCMAPFPlanner, GlobalCommunication, Metrics, PerfectChannel, run_episode

config = GridConfig(
    map=".....\n.....", num_agents=2,
    agents_xy=[[0, 1], [0, 2]], targets_xy=[[0, 4], [0, 0]],
    seed=7, obs_radius=2, max_episode_steps=20,
    observation_type="POMAPF", on_target="finish",
    collision_system="priority", integration=None,
)
env = SumOfCostsAndMakespanMetric(pogema_v0(grid_config=config))
try:
    env.reset(seed=config.seed)
    goals = env.unwrapped.get_targets_xy(ignore_borders=True)
    planner = DCMAPFPlanner(env.unwrapped.get_obstacles(ignore_borders=True),
                           goals, moves=config.MOVES)
    metrics = Metrics(goals, seed=config.seed,
                      intent_provider=planner.intended_steps)
    result = run_episode(env, GlobalCommunication(), PerfectChannel(),
                         planner, metrics, max_steps=config.max_episode_steps)
    out = Path("outputs/traces/planner_metrics_example.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": result, "raw": metrics.to_data()}, indent=2))
    print(result)
finally:
    env.close()
```

The recorder evaluates reachability, bounded eventual-progress liveness, safety
and stall diagnoses after the run. ISR/CSR come from POGEMA. Solved-run SoC and
makespan use the trace's first arrivals, correcting a verified bug in the pinned
cost wrapper: arrivals at steps 1 and 4 must give SoC 5, while the wrapper reports
8. The wrapper in the example is optional; its raw values remain available in
`environment_metrics` for comparison.

Save both the summary and raw bundle. Intentions cover decision rows only, with
no stale entry for the terminal state. Unsolved costs remain `None`, as do
success metrics and costs if a caller cuts off before POGEMA supplies terminal
ISR/CSR. `Metrics.from_data(raw_bundle).summary()` recomputes offline after a JSON
round trip, including from older raw bundles; regenerate older cost summaries.
See the [metrics contract](docs/TEAM_BUILD_GUIDE.md#metrics-and-monitors) for
window semantics, blocker evidence and the cost definition. Oracle integration
and statistical sweeps remain pending.

## Validation

From the repository root with the environment activated:

```powershell
python -m unittest discover -s tests -v
```

All 76 tests pass with Python 3.13.12 and the pinned POGEMA revision. Planner
episodes cover adjacent and more distant pockets, horizontal and vertical
corridors, waiting for a peer to pass, no-message stalls, and reset. The metrics
checks cover analytic robustness traces, staggered and initial-goal arrivals,
terminal intention filtering, native diagnostics and JSON persistence. Planner
episode tests use the existing test recorder and do not depend on the metrics module.

The README example and saved-trace reload also pass. These checks establish
behavior on selected fixtures; statistical comparisons and oracle validation
remain pending.

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
The verifier's 100-agent timing uses random actions, not `DCMAPFPlanner`.

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
- Make commits only when the user explicitly requests them. Never add AI coauthors.
