# Decentralized MAPF under Communication Constraints

Multi-Agent Systems course project at IIT Hyderabad. We study how communication
range, topology, and reliability affect decentralized robot coordination on a
grid, using POGEMA as the simulation environment.

The planned study keeps one decentralized planner fixed across global, none,
range-limited, and k-nearest-neighbour communication. LaCAM3 provides a separate
centralized comparison baseline.

## Current status

This repository currently contains the project proposal, specification, team
build guide, a modular POGEMA environment verifier, shared module interfaces,
global/no-communication models, a perfect channel, and demonstrations.
Environment verification is complete; see
[the recorded results](docs/ENVIRONMENT_CHECK_RESULTS.md). Shared interfaces match
the build guide. The episode runner, range/k-nearest communication models, the integrated planner,
monitoring suite, oracle integration, and experiment harness remain to be built.

## Layout

```text
decentralized_mapf/
  interfaces.py              Shared message, trace, communication, channel, and planner contracts
  communication.py           Global/no-communication models and reusable graph statistics
  channels.py                Perfect channel; inherits the base pass-through behavior
  __init__.py                Public imports for project modules
tests/
  test_communication.py       Communication links and directed-graph statistics checks
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

The definitions live in `decentralized_mapf/interfaces.py` and match section 3 of
the team build guide. `Message` and `StepRecord` define data formats.
`CommunicationModel` and `Planner` declare methods that concrete implementations
will override; calling their unimplemented methods raises `NotImplementedError`.
The base `Channel` already passes messages through unchanged, as specified by
the guide. Implementations can be added without duplicating these contracts.

Shared coordinates use map-relative `(row, column)` values without border padding.
POGEMA observation coordinates are relative to each robot's start and must be
converted before being used in a shared message. Communication links are directed:
`{0: [1], 1: []}` means robot 0 can send to robot 1, with no reverse link.

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

Robot IDs are the indices in `positions`. Every robot appears as a graph key,
including isolated robots; neither model adds self-links. No communication
returns `{0: [], 1: [], 2: []}` and leaves local observation settings independent.
These models select potential links; they do not deliver messages or move robots.

Future models can reuse `graph_stats` from `decentralized_mapf.communication`.
Mean degree counts outgoing links; components and connectivity use the undirected
view, including isolated robots. An empty graph has zero components and is not
connected. A single isolated robot is connected.

Run the communication tests from the repository root:

```powershell
python -m unittest discover -s tests -v
```

## Perfect channel

The communication model selects potential links; the channel determines which
supplied transmissions arrive. `PerfectChannel` delivers everything immediately:

```python
from decentralized_mapf import Message, PerfectChannel

channel = PerfectChannel()
channel.reset()  # Call at the start of each episode.
outgoing = [Message(sender=0, position=(0, 0), goal=(5, 5), sent_at=0)]
arrived = channel.deliver(outgoing, t=0)
```

It inherits the existing `Channel` implementation, preserving the same list,
message objects, order, duplicates, payloads, and `sent_at` values. It has no
queue or random state, so `reset()` is a no-op. A message supplied at timestep
`t` arrives in that call; the channel does not rewrite an older sending time.
Future loss/delay channels will implement the same interface.

The episode runner (the next step) will connect graph edges, per-recipient
transmissions, channel delivery, and robot inboxes.

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
