# Decentralized Multi-Agent Path Finding under Communication Constraints

**Project specification — Multi-Agent Systems course project**
**Duration:** 8 working weeks | **Team size:** 5 | **Total budget:** ~300 person-hours

---

## HOW TO READ THIS DOCUMENT

Every work item in this document is tagged **GREEN**, **AMBER**, or **RED**.

| Tag | Meaning |
|---|---|
| 🟢 **GREEN** | **The absolute bare minimum.** This is the project. If only the green items ship, we have a complete, defensible, submittable piece of work. Nothing green is optional. |
| 🟡 **AMBER** | Done only if green finishes on schedule. Each amber item is independently droppable — dropping one does not break anything else. |
| 🔴 **RED** | Stretch / aspirational. Attempted only if green *and* amber are complete with time to spare. Expected outcome: most red items will not happen, and that is fine. Red items exist so we can say "we considered X" in the report. |

**Scheduling rule:** never start an amber item while a green item is unfinished. Never start a red item before week 7.

---

## 1. THE RESEARCH QUESTION

> **How much communication does decentralized multi-robot coordination actually need, and how gracefully does it degrade when that communication becomes unreliable?**

This is a **measurement and ablation study**, not an attempt to prove an open conjecture. We systematically degrade the information available to agents and record how performance changes. This design cannot fail to produce a result — if performance collapses at 40% packet loss, that collapse *is* the finding.

### 1.1 The setting

N agents on a 2D grid. Each agent has its own start cell and its own goal cell (goals differ per agent). Agents move one cell per timestep (up/down/left/right/wait). Static obstacles block cells. There is **no central planner** — each agent decides its own next action from its own local information plus whatever its neighbours tell it.

### 1.2 What makes this a Multi-Agent Systems project rather than a pathfinding project

| Course topic | Where it appears |
|---|---|
| Graph theory & communication topology | The communication graph is a first-class object we construct, vary, and measure (degree, connectivity, component count) |
| Consensus | Local conflict resolution is framed and measured as a consensus protocol (rounds-to-agreement) |
| Distributed intelligence | No global controller; every agent acts on partial information |
| Fault / attack resilience | Packet loss, message delay, disconnection, agent failure |
| Formal methods / behavioural guarantees | One proved lemma (deadlock-freedom under bounded delay) |
| Distributed optimization | Agents locally negotiate a joint outcome none of them can compute alone |

---

## 2. CRITICAL TERMINOLOGY — DO NOT CONFLATE THESE

This section exists because merging these concepts is the single most likely way to produce muddled experiments.

### 2.1 Observation ≠ Communication

| | **Observation** | **Communication** |
|---|---|---|
| Definition | What an agent senses by itself | What other agents tell it |
| Source | The simulator | Code we write |
| POGEMA parameter | `obs_radius` (FOV size) | **Does not exist** — POGEMA's own README states: *"No information sharing occurs between the agents."* |
| Our control | Set once per experiment, usually held fixed | The primary independent variable |

**Implication:** we cannot easily create a "every agent sees everything" condition in POGEMA, because observation is local by construction. Our control condition is **global communication** — agents learn about distant agents by being *told*, not by *seeing*.

These must be two independent dials in the code from day one. A large fraction of interesting results come from varying one while holding the other fixed.

### 2.2 Movement delay ≠ Communication delay

The published MAPF robustness literature (k-robust, p-robust — see §8) is about a **robot physically moving late**. Our project is about a **message arriving late**. These are different problems. The report must state this distinction explicitly — it demonstrates the literature was read properly and is the clearest statement of where our contribution sits.

### 2.3 Collisions may be impossible — verify before designing metrics around them

In most MAPF simulators, including (we believe) POGEMA, a collision **cannot occur**: if two agents attempt to enter the same cell, the move is rejected and the agents remain in place. If this is true, a collision counter reads zero forever and measures nothing.

What actually manifests when coordination fails:

- **Deadlock** — two agents face off in a corridor, neither yields, both permanently stuck
- **Thrashing** — agents repeatedly step into each other's way, wasting timesteps
- **Non-arrival** — agents simply do not reach their goal before the step limit

**This must be verified on day one** (see §4.2). The headline metrics are success rate, makespan, and sum-of-costs — not collision count.

---

## 3. SYSTEM ARCHITECTURE

Five components. The planner is arguably the *least* risky of them, because a published design exists to copy (§7.2).

```
┌─────────────────────────────────────────────────────────┐
│ ExperimentHarness                                       │
│  - sweeps configs × seeds, writes results, makes plots  │
└───────────────┬─────────────────────────────────────────┘
                │
┌───────────────▼─────────────────────────────────────────┐
│ Simulation loop (wraps POGEMA)                          │
│                                                          │
│  each timestep:                                          │
│   1. positions ← env state                               │
│   2. edges ← CommunicationModel.get_edges(positions)     │
│   3. msgs ← agents compose messages                      │
│   4. msgs ← FailureModel.corrupt(msgs, edges)            │
│   5. deliver surviving msgs to recipients' inboxes       │
│   6. actions ← Planner.act(obs, inbox) for each agent    │
│   7. env.step(actions)                                   │
│   8. MetricsCollector.record(...)                        │
└──────────────────────────────────────────────────────────┘
```

### 3.1 `CommunicationModel` 🟢

Determines **who can hear whom** at a given timestep. Pure function of agent positions (and optionally the map, for line-of-sight variants).

```python
class CommunicationModel:
    def get_edges(self, positions: list[tuple[int,int]]) -> dict[int, list[int]]:
        """Return adjacency: agent_id -> list of agent_ids it can send to.
        Must be deterministic given positions. Randomness belongs in FailureModel."""

    def graph_stats(self, edges) -> dict:
        """mean_degree, n_components, is_connected (undirected view for connectivity)"""
```

Required modes:

| Mode | Tag | Description |
|---|---|---|
| `global` | 🟢 | Everyone hears everyone. **Control condition.** |
| `none` | 🟢 | No communication at all. **Lower bound.** |
| `range_r` | 🟢 | Manhattan distance ≤ r (the implemented distance convention) |
| `knn_k` | 🟢 | k nearest agents by Manhattan distance, ties by ID (links may be asymmetric) |
| `ring` / `grid` | 🟡 | Fixed topology by agent index, ignores position |
| `line_of_sight` | 🟡 | Range-based, but obstacles block messages |
| `budget_b` | 🟡 | Each agent may send at most b messages per step; needs a selection rule |

**Implementation mapping:** `global`, `none`, `range_r`, and `knn_k` correspond
to `GlobalCommunication()`, `NoCommunication()`, `RangeCommunication(r=...)`,
and `KNNCommunication(k=...)`, exported by `decentralized_mapf`. These are research
mode labels, not an implemented configuration factory. The frozen API is in
`TEAM_BUILD_GUIDE.md` §3; diameter from the earlier architecture sketch is outside
that API. See §6/C8 of the guide for topology behavior, pending integration work,
and the matched-mean-degree comparison required before sweeps.

**Design note:** `graph_stats` is not decoration. Reporting mean degree and connectivity alongside performance is what converts a description ("performance drops at range 3") into an explanation ("performance drops when the communication graph fragments into more than ~4 components"). This is the graph-theory content of the project.

### 3.2 `Planner` 🟢

Decides one agent's next action from its observation and inbox.

```python
class Planner:
    def act(self, agent_id, observation, inbox, goal) -> Action
```

| Planner | Tag | Description |
|---|---|---|
| `IndependentAStar` | 🟢 | A* to own goal, ignore everyone. Sanity baseline; expect frequent deadlock. |
| `DCMAPF` | 🟢 | **Primary planner.** A* independently + local conflict resolution with communicating neighbours. Published design — see §7.2. |
| `PriorityYield` | 🟢 | Simple tie-break rule used inside DCMAPF: on conflict, lower-priority agent waits or sidesteps. Priority = agent index, or distance-to-goal, or negotiated. |
| `LearnedGating` | 🔴 | Small learned function deciding which neighbours to listen to |

### 3.3 `FailureModel` 🟡 (interface 🟢)

Corrupts the message stream. **The empty/no-op version is GREEN** — the interface must exist from week 1 so that adding failures later requires no refactor. The actual failure modes are amber.

```python
class FailureModel:
    def corrupt(self, messages, edges, t) -> list[Message]:
        """Drop, delay, or withhold messages. Returns surviving deliverable set."""
```

| Failure mode | Tag | Parameterization |
|---|---|---|
| No-op (perfect channel) | 🟢 | — |
| Packet loss | 🟡 | Each message independently dropped with probability p. Sweep p ∈ {0, 0.1, 0.2, 0.4, 0.6, 0.8} |
| Message delay | 🟡 | Message sent at t arrives at t+d. Agents therefore act on stale positions. |
| Disconnection | 🟡 | Agent goes comms-dark for a window of W timesteps |
| Agent failure | 🟡 | Agent stops moving entirely, becomes a dynamic obstacle |
| Byzantine / false info | 🔴 | Agent broadcasts incorrect position or intent. **See §9 — likely cut.** |

These must be **independent switches**, combinable but individually testable.

### 3.4 `MetricsCollector` 🟢

See §6 for full metric definitions.

### 3.5 `ExperimentHarness` 🟢

Runs the config × seed sweep, persists raw results to disk, aggregates, plots.

**Non-negotiable requirements:**
- Every run takes an explicit seed. Every result row records its seed.
- Raw per-run results are written to disk before aggregation, so plots can be regenerated without re-running.
- Configs are declared in data (YAML/JSON), not hardcoded in scripts.

🟡 **Optional accelerator:** `pogema-toolbox` (`github.com/Cognitive-AI-Systems/pogema-toolbox`) already provides custom map registration, parallel multi-instance execution via Dask, result aggregation, and plotting. Evaluate it in week 1. If it fits, it removes most of this component. If it fights us, write ~200 lines ourselves and move on — do not spend more than one day deciding.

---

## 4. ENVIRONMENT SETUP

### 4.1 Installation 🟢

```bash
pip install git+https://github.com/Cognitive-AI-Systems/pogema.git
```

⚠️ **Do NOT use `pip install pogema`.** The PyPI package still contains an older version while the maintainers finish POGEMA 2.0. Many tutorials and forks (including `AIRI-Institute/pogema`) still instruct the PyPI install — ignore them.

⚠️ **Repository disambiguation.** Three GitHub repos share this name:
- `AIRI-Institute/pogema` — a fork, ~40 stars, outdated install instructions
- `CognitiveAISystems/pogema` — a stub whose README only redirects
- ✅ `Cognitive-AI-Systems/pogema` — **the real one.** 299 stars, MIT licence, ICLR-2025, active docs at `cognitive-ai-systems.github.io/pogema/`

Minimal working example:

```python
from pogema import pogema_v0, GridConfig

grid_config = GridConfig(
    num_agents=8,
    size=32,
    density=0.3,
    seed=42,
    max_episode_steps=256,
    obs_radius=3,        # observation FOV — NOT communication
)
env = pogema_v0(grid_config=grid_config)
obs, info = env.reset()
while True:
    obs, reward, terminated, truncated, info = env.step(env.sample_actions())
    if all(terminated) or all(truncated):
        break
```

### 4.2 Day-one verification checklist 🟢

**Complete this before writing the proposal or any other code.** Write the answers into a file called `ENVIRONMENT_CHECK_RESULTS.md` and commit it.

1. Does a 100-agent episode complete? How many wall-clock seconds?
2. **What happens when two agents attempt to enter the same cell?** Rejected move, or actual collision? → This determines whether "collision rate" is a real metric.
3. Can agent positions and goals be read externally every timestep?
4. Can a custom per-agent action be injected each step, or does the API force us through a policy interface?
5. Is there a deterministic seeding path such that the same seed reproduces the same instance exactly?
6. What exactly is in `info` after `step()` and `reset()`? Which metrics come free?

If all six are acceptable, the project is de-risked. If any fails, we learn it on day one rather than week four, and adapt the plan.

---

## 5. EXPERIMENT MATRIX

### 5.1 🟢 GREEN — the minimum viable set

| # | Experiment | Independent variable | Purpose |
|---|---|---|---|
| E1 | Sanity ladder | {oracle, global comms, no comms} | Validates the entire pipeline. Bars must come out in that order. |
| E2 | Communication range sweep | r ∈ {1, 2, 3, 5, 8, ∞} | **The core result.** Performance vs how far messages carry. |
| E3 | Topology comparison | {range, k-NN, global} at matched mean degree | Does *structure* matter, or only *quantity* of communication? |
| E4 | Agent-count scaling | N ∈ {10, 25, 50, 100} × comms settings | Does the communication requirement grow with density? |
| E5 | Graph-property correlation | Plot performance against mean degree / component count | Converts description into explanation |

Minimum rigour: **3 map types × 5 seeds × every config.** Same maps, same starts, same goals across all communication settings (matched instances).

### 5.2 🟡 AMBER — the resilience story

| # | Experiment | Independent variable |
|---|---|---|
| E6 | Packet loss sweep | p ∈ {0, 0.1, 0.2, 0.4, 0.6, 0.8} — is degradation graceful or a cliff? |
| E7 | Message delay sweep | d ∈ {0, 1, 2, 5} timesteps |
| E8 | Disconnection | Random comms blackouts of length W |
| E9 | Agent failure | f% of agents freeze mid-episode |
| E10 | Consensus measurement | Rounds-to-agreement in the conflict-resolution step vs comms quality |
| E11 | Combined degradation | Loss + delay together — do they compound or interact? |
| E12 | Message-content ablation | Broadcast position only / + goal / + full planned path |

**A cliff in E6 is a better finding than a smooth slope.** Either way it is a result.

### 5.3 🔴 RED — stretch

| # | Experiment |
|---|---|
| E13 | Learned communication gating vs fixed distance threshold, small N only |
| E14 | Byzantine agents broadcasting false positions |
| E15 | Dynamic environments — obstacles appearing, agents entering/leaving |
| E16 | Lifelong MAPF — agents receive new goals on arrival |
| E17 | Adaptive comms — agents learn *when* to stay silent to save budget |

---

## 6. METRICS

**Metrics are where student projects die. This section is not the easy part.**

### 6.1 🟢 Primary metrics

| Metric | Definition | Notes |
|---|---|---|
| **Success rate** | Fraction of agents reaching goal within step limit | Headline number. Standard across the MAPF literature, so comparable to published results. |
| **Makespan** | Timestep at which the *last* agent arrives | Standard MAPF metric |
| **Sum-of-costs (SoC)** | Total timesteps summed over all agents | Standard MAPF metric |
| **Deadlock count** | Agents with zero net displacement over the final K timesteps while not at goal | Replaces "collision count" if collisions are impossible |
| **Communication overhead** | See §6.2 | The metric the research question depends on |

### 6.2 🟢 Defining communication overhead

There is **no standard definition**. We must choose one and defend it in the report. Recommended: report all three, lead with the first.

1. **Messages per agent per timestep** — simple, interpretable, hardware-agnostic
2. **Total messages per solved instance** — captures that a slower solution also talks longer
3. **Bytes transmitted** — requires assigning a size to each message type; only meaningful for the message-content ablation (E12)

**Do not build a telecom simulator.** A message is a small struct: sender id, position, goal, optionally next planned cell. Count them. That is sufficient.

### 6.3 🟢 Statistical discipline — non-negotiable

- **Seeds:** minimum 5 per configuration; 10 preferred. Single runs tell us nothing — inter-seed variance is frequently larger than the effect being measured.
- **Matched instances:** identical map, starts, and goals across every communication setting within a comparison. Otherwise we are comparing noise.
- **Error bars on every plot.** Standard error or 95% CI, stated in the caption.
- **Timeout policy:** declare the step limit up front and declare how timed-out runs enter the averages. Silently dropping failures inflates results — this is a classic error and an attentive examiner will look for it. Recommended: report success rate separately, and compute makespan/SoC over *solved instances only*, always alongside the success rate.

### 6.4 🟡 Secondary metrics

- Rounds-to-consensus in the conflict-resolution step
- Wall-clock planning time per agent per step
- Path-length ratio vs the centralized oracle (how much is decentralization costing us?)
- Message delivery ratio (sanity check on FailureModel)

---

## 7. BASELINES

### 7.1 Centralized oracle 🟢

**Use LaCAM3 via its Python bindings** — the `pybind` branch of `github.com/Kei18/lacam3` (Python interface added March 2025). Provides near-optimal centralized solutions at large scale.

⚠️ **Do not use `pylacam`.** Its own README states it replaces PIBT with random action selection to keep the implementation simple. It is a teaching toy, not a credible upper bound.

⚠️ **Do not use `mapf-IR`** as a live dependency. It was archived read-only by its author on 5 Oct 2025, it is C++ with a macOS-only visualizer, and its algorithms are superseded by LaCAM3. It remains useful as a *reference* for classical algorithm implementations (CBS, ECBS, PIBT, HCA*).

The oracle answers: **what does perfect global information buy you?** Every decentralized result is reported as a ratio against it.

### 7.2 Decentralized baseline 🟢 — DCMAPF

Our primary planner, taken from Maoudj & Christensen (see §8). The design:

1. Each robot independently plans its own path with A*, **ignoring all other robots**
2. Robots resolve potential conflicts **locally, as they occur**, coordinating only with neighbours inside a limited communication radius

Why this is the right choice:
- Simple enough to implement in roughly one week
- **Published with results** — the authors report high success rates across maps and fleet sizes, outperforming the prioritized planners PIBT and PIBT+ on solution quality, with the exception of very small dense maps at high robot counts. We can sanity-check our implementation against those reported trends.
- Non-learned, so the communication ablation is clean — any performance change is attributable to information, not to training variance
- Communication radius is *already* the central parameter, which is exactly our independent variable

### 7.3 Naive lower bound 🟢

`IndependentAStar` with zero communication. Expect frequent deadlock. Establishes the floor.

---

## 8. REFERENCES

### 8.1 Core — the baseline algorithm

**Decentralized Multi-Agent Path Finding in Warehouse Environments for Fleets of Mobile Robots with Limited Communication Range**
Maoudj, A. & Christensen, A. L. — ANTS 2022 (Swarm Intelligence conference), Málaga
DOI: `10.1007/978-3-031-20176-9_9`
⚠️ A correction was published (`10.1007/978-3-031-20176-9_34`) fixing a software error in the original quantitative results. **Read the corrected figures, not the originals.**

**Improved decentralized cooperative multi-agent path finding for robots with limited communication**
Maoudj & Christensen — *Swarm Intelligence* journal, 2023
`https://link.springer.com/article/10.1007/s11721-023-00230-7`
The extended journal version. Each robot coordinates solely with neighbours inside a limited communication radius.

### 8.2 Environment

**POGEMA: A Benchmark Platform for Cooperative Multi-Agent Pathfinding**
Skrynnik, Andreychuk, Borzilov, Chernyavskiy, Yakovlev, Panov — **ICLR 2025**
`https://openreview.net/forum?id=6VgwE2tCRm` | arXiv: `2407.14931`
Earlier version: arXiv `2206.10944` (2022)
Code: `https://github.com/Cognitive-AI-Systems/pogema` (MIT)
Toolbox: `https://github.com/Cognitive-AI-Systems/pogema-toolbox`
Benchmark: `https://github.com/Cognitive-AI-Systems/pogema-benchmark`

### 8.3 Centralized oracle

**Engineering LaCAM\*: Towards Real-Time, Large-Scale, and Near-Optimal Multi-Agent Pathfinding**
Okumura, K. — AAMAS 2024 | `https://github.com/Kei18/lacam3` (MIT, use `pybind` branch)

Lineage: LaCAM (AAAI 2023) → LaCAM2 (IJCAI 2023) → LaCAM3 (AAMAS 2024)

### 8.4 Learned communication — related work, NOT to be reimplemented

**Distributed Heuristic Multi-Agent Path Finding with Communication (DHC)**
Ma, Z., Luo, Y., Ma, H. — ICRA 2021 | arXiv `2106.11365` | `github.com/ZiyuanMa/DHC`
Graph-convolution communication. Note their own justification: full communication with neighbours creates large overhead and latency, so they select only the nearest two neighbours.

**Learning Selective Communication for Multi-Agent Path Finding (DCC)**
Ma, Z., Luo, Y., Pan, J. — IEEE RA-L | arXiv `2109.05413` | `github.com/ZiyuanMa/DCC`
⚠️ **Most important paper to cite.** Decision Causal Communication lets agents select which neighbours to communicate with during both training and execution — a neighbour counts as relevant only when its presence actually changes the agent's decision. **This is essentially the RED "learned gating" idea, already done.** Cite it; do not claim novelty here.

**SCRIMP** — transformer-based communication from very small FOVs, with state-value tie-breaking
**PICO** — folds planning priorities and communication topologies into the learning pipeline
**MAPF-GPT** (AAAI 2025) / **MAPF-GPT-DDG** (IROS 2025) — imitation learning from LaCAM, notably *without* agent communication. Useful contrast point.

### 8.5 Robustness — note the distinction in §2.2

**Robust Multi-Agent Path Finding** — Atzmon, Stern, Felner — AAMAS 2018
`https://ifaamas.org/Proceedings/aamas2018/pdfs/p1862.pdf`
Introduces **k-robust** plans: a plan remains valid under up to k unexpected delays per agent.

**Robust Multi-Agent Path Finding and Executing** — Atzmon et al. — *JAIR* 67:549–579, 2020

**Probabilistic Robust Multi-Agent Path Finding** — ICAPS 2020
`https://idm-lab.org/bib/abstracts/papers/icaps20b.pdf`
Introduces **p-robust**: probability of no conflict ≥ p. Argued as more realistic than assuming a hard delay cap.

**Multi-Agent Path Finding with Delay Probabilities** — Ma, Kumar, Koenig — AAAI 2017

⚠️ All of the above concern **movement** delays. Our project concerns **communication** delays. State this explicitly in the report.

### 8.6 Communication failure — theory backing the amber work

**Provably Safe Multi-Robot Coordination With Unreliable Communication** — IEEE RA-L
`https://ieeexplore.ieee.org/document/8744598/`
Proves safety is guaranteed when communication errors are limited to delays, and bounds the probability of unsafety as a function of the channel model under packet loss.
**Use this as the template for our one formal lemma.**

**Distributed Algorithms for Consensus and Coordination in the Presence of Packet-Dropping Communication Links**
Domínguez-García, Hadjicostis, Vaidya — arXiv `1109.6391`
Consensus theory under lossy links. Backs the consensus framing.

### 8.7 Communication-constrained MAPF — the harder variant

**Multi-Agent Pathfinding Under Team-Connected Communication Constraint via Adaptive Path Expansion and Dynamic Leading**
arXiv `2501.02770` (v5, Feb 2026)
Requires the *whole team* to remain communication-connected throughout. Handles up to 25 agents under limited communication range, exceeding 90% success where baselines fail.
**Related work only — too hard for our main track.**

---

## 9. RISK REGISTER

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | Weeks lost to environment setup | High | §4.2 day-one environment check. Hard cap: if POGEMA is not running in 3 days, escalate. |
| R2 | Collision metric turns out meaningless | Medium | Verified in environment check Q2. Metrics already designed around success rate instead. |
| R3 | Results too noisy to claim anything | **High** | 5+ seeds from week 1, matched instances, error bars on everything. Not retrofittable. |
| R4 | ML component consumes the project | **High** | ML is RED. Never started before week 7. Bounded as one experiment, not a subsystem. |
| R5 | Interface churn breaks parallel work | High | Freeze the environment/module interfaces at end of week 1. Changing them in week 5 costs four people a week. |
| R6 | Scope creep across amber items | Medium | Amber items are individually droppable by design. Drop, do not descope-partially. |
| R7 | Reimplementing published work without knowing | Medium | DCC already does learned selective communication. Read §8.4 before claiming novelty. |
| R8 | Byzantine rabbit hole | Medium | Byzantine is RED and probably cut. It is a separate research field with its own machinery. |
| R9 | Feature work continuing into the writing window | **High** | **Hard code freeze at start of week 7.** After that: runs, plots, and prose only. |
| R10 | Dependency rot on abandoned repos | Low | Verified: use `Cognitive-AI-Systems/pogema` + `lacam3`. Avoid Flow (last release Sept 2019), `mapf-IR` (archived Oct 2025), `pylacam` (toy planner). |

---

## 10. IMPLEMENTATION SEQUENCE

Ordering only. Work distribution is deliberately out of scope for this document.

### Week 0 — Environment checks 🟢
Complete §4.2 checklist. Commit `ENVIRONMENT_CHECK_RESULTS.md`. Do not proceed until all six questions are answered.

### Weeks 1–2 — Skeleton and control conditions 🟢
- `CommunicationModel` with `global` and `none` modes only — get the plumbing right before adding physics
- `FailureModel` interface as a no-op (so adding failures later requires no refactor)
- `IndependentAStar` + `DCMAPF` planners
- `MetricsCollector` with seeds and matched instances from the start
- LaCAM3 oracle wired in
- **Freeze all module interfaces at end of week 1**

**Exit criterion:** E1 produces one plot — 10 agents, three bars: oracle / global comms / no comms, with error bars, in the correct order. This single plot validates the entire pipeline. Everything afterwards is turning dials.

### Weeks 3–4 — Topology 🟢
- Add `range_r` and `knn_k` modes
- Implement `graph_stats`
- Run E2, E3, E4, E5

**Exit criterion:** performance-vs-communication-range curves with error bars. **This alone is a passing project.** Everything after is upside.

### Weeks 5–6 — Resilience 🟡
- Implement packet loss, delay, disconnection, agent failure as independent switches
- Run E6–E9, then E10–E12 if time
- Frame conflict resolution as a consensus protocol; measure rounds-to-agreement
- Prove **one** lemma — e.g. *"under full communication and message delay bounded by d, the yield rule cannot deadlock."* One lemma, ~10 hours, using §8.6 as the template. Not a paper's worth of theory.

🟡 Amber topology modes (`ring`, `grid`, `line_of_sight`, `budget_b`) slot in here if there is room.

### Weeks 7–8 — Scale, analysis, write-up 🟢
- **CODE FREEZE at start of week 7.** No new features. Runs, plots and prose only.
- Final sweeps: N ∈ {10, 25, 50, 100} × 3 map types × 5+ seeds
- Plots, then report

🔴 Red items are attempted here only if green and amber are fully complete. Realistic expectation: they will not be.

---

## 11. ENGINEERING RULES

1. **Everything takes a seed.** Every run, every plot, every recorded number. Unseeded results are unreproducible, and an anomalous curve in week 7 will be undebuggable.
2. **Freeze interfaces in week 1.** Everyone codes against them thereafter.
3. **Write raw results to disk before aggregating.** Plots must be regenerable without re-running experiments.
4. **Configs live in data files, not in code.** One YAML/JSON per experiment.
5. **Observation and communication stay separate dials.** Never let one implicitly control the other.
6. **Do not build a telecom simulator.** Messages are small structs. Count them.
7. **Green before amber, always. Amber before red, always.**

---

## 12. WHAT "DONE" LOOKS LIKE

**Minimum (green only) — a complete, submittable project:**
A systematic characterisation of how decentralized MAPF performance depends on communication range and topology, benchmarked against a centralized oracle and a no-communication floor, across agent counts and map types, with graph-theoretic properties of the communication network correlated against performance outcomes.

**Target (green + most amber):**
The above, plus a resilience study showing how that performance degrades under packet loss, message delay, disconnection, and agent failure — with the conflict-resolution mechanism framed and measured as a local consensus protocol, and one proved deadlock-freedom property.

**Stretch (some red):**
The above, plus a single bounded experiment on whether learned communication gating outperforms a fixed distance threshold — explicitly positioned as a reproduction-and-extension of DCC, not as a novel contribution.
