# Decentralized MAPF under Communication Constraints — Team Build Guide

**Read §1, §3, §3.5 and §4 before writing any code.** §3 (the frozen interfaces) is the
most important part of this document. If everyone codes against it, the five
modules snap together. If anyone deviates, integration breaks.

---

## 1. Notation

Two prefixes, used everywhere in this project and in the proposal.

| Prefix | Meaning |
|---|---|
| **C** | **Core.** Committed. This is the project. If only the C steps ship, the project is complete and submittable. Nothing in C is optional. |
| **E** | **Extension.** Attempted only after the core is done. Each E is independently droppable — dropping one breaks nothing else. Expect some E steps not to happen, and that is fine. |

### Core steps

| | Step | One-line description |
|---|---|---|
| **C1** | Environment setup | POGEMA installed, verified at 100 agents, collision behaviour confirmed |
| **C2** | Communication layer | Positions → who-can-hear-whom. Modes: `global`, `none` |
| **C3** | Channel interface | Empty pass-through stage every message goes through |
| **C4** | Planner | Per-robot A\* plus a yield rule for conflicts with known neighbours |
| **C5** | Spec monitors, deadlock detector & metrics | STL monitors over the run trace; success rate, makespan, SoC, message count, robustness |
| **C6** | Oracle & floor | LaCAM3 ceiling, zero-communication floor |
| **C7** | Experiment harness | Config-driven sweeps, seeding, matched instances, plots |
| **C8** | Range & k-NN topologies + graph stats | The other two topologies, plus degree/components/connectivity |
| **C9** | Sweeps, analysis, report | Run the grid, make the success-rate and robustness curves, write it up |

**The four topologies live in C2 and C8:** `global` and `none` in C2;
`range-limited` and `k-nearest-neighbour` in C8.

**Formal methods are not a separate step, and they are not an extension.**
Temporal logic lives inside C5, C7 and C9; epistemic logic is the frame around
C2, C8 and the C9 write-up. See **§3.5**. This is graded content: the professor
approved the proposal on the condition that we explain how formal methods enter,
and we have replied in writing committing to it. Nothing in §3.5 is droppable.

### Extension steps

| | Step |
|---|---|
| **E1** | Packet loss — drop each message with probability *p*, swept 0 → 0.8 |
| **E2** | Message delay — arrives *d* steps late; robots plan on stale info |
| **E3** | Disconnection — robot goes comms-dark for a window of steps |
| **E4** | Agent failure — robot freezes permanently into an obstacle |
| **E5** | Consensus framing — count rounds-to-agreement in the yield rule |
| **E6** | Deadlock-freedom proof — one lemma, on paper, no code |
| **E7** | Message-content ablation — position only vs +goal vs +full path |

---

## 2. Assignment

| Who | Core | Extensions |
|---|---|---|
| **Ronit** | C1, C2, C3 | E1, E2 |
| **Harsh** | C4, C5 | E3, E4 |
| **Dhanvi** | C6 | E5 |
| **Charitha** | C7 | E6 |
| **Maanya** | C8 | E7 |

### Who reports which result (the C9 split)

| Result | Owner |
|---|---|
| Three-bar validation: oracle / global / none | Ronit + Harsh |
| Deadlock characterisation: where and how often | Harsh |
| Range sweep + topology comparison (**the headline curves**) | Maanya |
| Agent-count scaling (10 / 25 / 50 / 100) | Charitha |
| Oracle ratios + **overall synthesis** | Dhanvi |

**Synthesis means:** one sentence answering *how much communication does
decentralized coordination actually need*, with the other four sections
supporting it. Without a named owner you get five disconnected sections stapled
together. This is Dhanvi's job.

### Formal methods ownership

Nobody gets a new module. The work folds into steps that already exist:

| Piece | Owner | Where it lives |
|---|---|---|
| The STL monitors themselves | Harsh | C5 — they *are* the metric suite |
| Trace persistence + robustness columns | Charitha | C7 |
| Epistemic deadlock split (information absent vs rule failed) | Harsh, used by Dhanvi | C5 → C9 synthesis |
| Robustness curve beside the success-rate curve | Maanya | C9 headline |
| Trace fields in the frozen record | Ronit | §3, before the freeze |

---

## 3. FROZEN INTERFACES — do not change after everyone starts

Paste this block into your LLM prompt every single time. It is the contract
between the five modules.

```python
from dataclasses import dataclass, field

# ---------------------------------------------------------------- messages
@dataclass
class Message:
    """One robot telling another where it is and where it's going.
    Add FIELDS if needed (E7 does), never change existing names."""
    sender: int
    position: tuple[int, int]
    goal: tuple[int, int]
    next_cells: list[tuple[int, int]] = field(default_factory=list)
    sent_at: int = 0          # timestep sent; E2 needs this
    recipient: int | None = None  # runner sets this on each per-edge transmission


# ------------------------------------------- C5: one row of the run trace
@dataclass
class StepRecord:
    """Everything the offline spec monitors (§3.5) need for one timestep.
    Frozen: the monitors and the harness both read this. If a field is
    missing here, that specification cannot be evaluated afterwards."""
    t: int
    positions: list[tuple[int, int]]
    mean_degree: float
    n_components: int
    n_messages: int
    inbox_senders: dict[int, list[int]]   # who each robot actually heard
    max_age: int = 0                      # max (t - sent_at) delivered; E2


# ------------------------------------------------- C2 / C8: who hears whom
class CommunicationModel:
    """Pure function of positions. NO randomness here — that belongs in
    the channel (C3). Same positions must always give same edges."""

    def get_edges(self, positions: list[tuple[int, int]]) -> dict[int, list[int]]:
        """Return {sender_id: [receiver_ids]}.
        IDs index the supplied positions; the runner maps active subsets back
        to original robot IDs after topology selection.
        NOTE: may be asymmetric (k-NN is). Do not assume i in edges[j]
        implies j in edges[i]."""
        raise NotImplementedError

    def graph_stats(self, edges: dict[int, list[int]]) -> dict:
        """{'mean_degree': float, 'n_components': int,
            'is_connected': bool}"""
        raise NotImplementedError


# ------------------------------------------------ C3: the channel (+E1-E4)
class Channel:
    """Corrupts the message stream before delivery.
    Base class delivers everything unchanged (C3 = no-op)."""

    def deliver(self, messages: list[Message], t: int) -> list[Message]:
        """Return the subset of messages that actually arrive at step t."""
        return messages

    def reset(self) -> None:
        """Clear any internal queues between episodes."""
        pass


# --------------------------------------------------------- C4: the planner
class Planner:
    """ONE planner for ALL topologies. It reads its inbox and does not
    know or care why the inbox is full or empty. This is why the
    experiment is valid: any performance change is due to INFORMATION."""

    def reset(self) -> None:
        """Clear episode-specific state; override if the planner keeps caches."""
        pass

    def observe(self, agent_id: int, observation, position: tuple[int, int],
                goal: tuple[int, int]) -> None:
        """Refresh this robot's local state before compose(); do not take action.
        position/goal are map-relative; observation stays start-relative."""
        pass

    def act(self,
            agent_id: int,
            observation,                 # POGEMA POMAPF dict
            inbox: list[Message],
            goal: tuple[int, int]) -> int:
        """Return a POGEMA action int. MUST handle inbox == [] gracefully."""
        raise NotImplementedError

    def compose(self, agent_id: int, t: int) -> Message:
        """What this robot broadcasts this step."""
        raise NotImplementedError
```

### The simulation loop (Ronit owns this)

Use the implementation in `decentralized_mapf/runner.py`, rather than copying
an episode loop into each module:

```python
from decentralized_mapf import run_episode

result = run_episode(env, comm, channel, planner, metrics, max_steps=256)
```

The environment must be seeded POMAPF with `on_target='finish'`. The runner resets
the environment and channel, calls `planner.reset()`, then for each decision step:
reads map-relative positions; calls `observe()` for all active robots; composes,
routes and delivers messages; records the current state and deliveries; asks
for actions; and steps the environment. It also records the final state with
empty deliveries, so K steps produce K+1 records. Use a fresh recorder per run.

**Integration additions:** existing `act`, `compose`, `deliver`, and `record`
signatures are unchanged. `Message.recipient` is an optional field, as allowed
by the message contract. `Planner.reset` and `Planner.observe` are additive hooks
with no-op defaults. Implement `observe` to refresh each robot's own position and
intended path before its broadcast; an attempted move may have been blocked.
Do not use other robots' private state when planning. Keep observations in
their original POGEMA frame and use the supplied own position for shared messages.

Finished robots retain stable IDs and final positions in the trace but are
excluded from topology selection and inbox delivery. The runner passes active
positions to `get_edges()` in original ID order, then maps the returned local
indices back to stable robot IDs for routing and statistics. Graph statistics
therefore describe active robots. Exclude the terminal record when aggregating
decision-step statistics, and exclude hidden finished robots from safety checks.

*Note on `metrics.record`:* it takes `arrived` and `inboxes`, not a message
count. A count cannot tell you message age (needed for the E2 freshness spec) or
who a robot actually heard from (needed for the epistemic deadlock split in
§3.5), and neither is recoverable after the episode ends. Take the length inside
`record`. **Get this into the frozen block on day one** — adding it later is a
signature change, which rule 2 forbids.

*Routing:* **each edge carries its own droppable message**, with an independent
payload snapshot and explicit `recipient`. Channels preserve this address even
when delaying delivery. Route arrivals by `recipient`, never by matching a sender
against the current graph: that duplicates broadcasts and misroutes stale messages.

---

## 3.5 FORMAL METHODS — temporal logic and epistemic logic

Read this even if your step has no code in it. The professor asked specifically
how formal methods enter the project before approving it, and he is pushing on
this, so it is being graded whether or not it appears in the rubric. We have
already replied committing to what follows. Treat it as a promise, not an idea.

The cheap part is that it costs almost no new code. Our metric suite is already
a set of properties over signals; stating them as temporal-logic formulas makes
them precise, gives them a *quantitative* reading we do not currently have, and
turns "the robot got stuck" into a claim with a definition behind it.

### What we committed to, in writing

1. **Epistemic logic frames the independent variable.** The communication graph
   at each timestep decides what each robot knows, so a deadlock is an
   *epistemic failure*: the fact needed to resolve the conflict did not reach
   the robot in time.
2. **STL supplies the monitored specs:** goal reachability, and a no-stall
   liveness property that serves as our deadlock detector.
3. **Robustness is reported alongside binary success rate,** because robustness
   records how near a failed run came to satisfying the formula — e.g. how close
   a robot got to its goal before the episode timed out.

Nothing beyond these three was promised. Message freshness and the
deadlock-freedom lemma were deliberately left out of the reply because they sit
in E2 and E6 and may not ship. Do not volunteer them until they exist.

### The signals

Distances and deliveries are computed offline from the frozen `StepRecord` trace
in §3. Blocker attribution also needs the intention sidecar described under Metrics and monitors;
positions and sender IDs alone cannot reconstruct which cell a robot planned to enter.

```
d_i(t)     = manhattan(positions[i], goals[i])      # distance to goal
sep(t)     = min over pairs (i,j) of manhattan(p_i, p_j)
age_ij(t)  = t - m.sent_at                          # zero under C3; E2 only
```

### The specifications

```
phi_reach_i  =  F_[0,T] ( d_i(t) <= 0 )                     # it arrives
phi_live_i   =  G_active ( F_[1,W] ( d_i(t+k) < d_i(t) ) )  # progress before arrival
phi_safe     =  G ( sep(t) >= 1 )                           # no co-occupancy
```

`phi_live` **is** the shared stall detector. It tests for an eventually-closer
position within each complete W-step window, starting before first arrival. A
violation is a finite-trace stall signal, not proof of permanent deadlock; a
necessary detour can violate it. Only unfinished agents with a violation are
counted by `deadlocked_agents`. `phi_safe` is
structurally true in POGEMA (gotcha 5), so it is not a result; it is a monitor on
our own implementation, and if it ever fires we have a bug in the loop.

### Robustness (quantitative semantics)

Satisfied iff the value is `>= 0`. Larger is further inside the spec.

```
rho_reach_i =  -min over t of d_i(t)
               # 0 means arrived. -3 means it got within three cells and stopped.
               # Bounded above by 0 by construction; it is a shortfall measure.

rho_live_i  =  min_k max_{j=k+1,...,k+W} ( d_i(k) - d_i(j) - 1 )
               # >= 0: every evaluated window has a closer position.
               # < 0: at least one complete window has no closer position.

rho_safe    =  min over t of ( sep(t) - 1 )
               # >= 0 always, in a correct implementation.
```

**Liveness semantic correction (before sweeps):** the earlier endpoint expression
`d(k)-d(k+W)` did not implement the stated eventually formula: it ignored progress
inside the window. Its zero-as-failure rule also contradicted the shared `>=0`
satisfaction convention. The implementation follows the formula above; subtracting
one encodes strict progress on integer Manhattan distances. Its version is
`bounded_eventual_progress_v1` in summaries and saved bundles. No complete window
means `None` (unknown), not success or failure. Post-arrival windows are excluded.
Safety excludes robots on and after first arrival under `on_target="finish"`.

Report **mean `rho_reach` over agents**, per run, next to ISR and CSR. This is
the number that answers "how *gracefully* does it degrade" rather than "did it
work", and it is the headline justification for having specs at all: two
settings can both score ISR 0.4 while one leaves its failed robots one cell short
and the other leaves them stranded across the map.

### The epistemic frame

Write `K_i(phi)` for "robot i knows phi". The only proposition the yield rule
consumes is a neighbour's claimed next cell, so that is the only one we track.

| Topology | Epistemic condition on a conflicting pair |
|---|---|
| `global` | each claim is mutual knowledge within one step |
| `range-limited`, `k-NN` | a claim reaches direct neighbours only; inside a component it is at best *distributed* knowledge |
| `none` | private observation only; `K_i` is empty |

This is what makes the graph statistics explanatory rather than descriptive:
`n_components` is a bound on what is knowable, not just a number that correlates
with failure.

**Deadlock classification**, evaluated at the step a stall begins, from
`inbox_senders`:

- **Epistemic failure** — the blocking neighbour is not in the agent's inbox.
  This records a missing one-hop claim; it does not distinguish topology from
  channel loss, nor prove that receiving the claim would have resolved the stall.
- **Rule failure** — the neighbour *was* in the inbox and the yield rule stalled
  anyway. Investigate the planner and map constraints before the sweeps; this
  is not by itself proof of a coding bug or that the instance was solvable.
- **Unattributed** — no blocker can be identified from saved pre-decision
  intentions. Keep this category; do not turn missing evidence into an epistemic
  failure. Report its count alongside the split.

The ratio between these two is Harsh's deadlock characterisation and the spine
of Dhanvi's synthesis.

**One-hop caveat, and it matters.** Our loop fills inboxes from direct edges
only — there is no relaying. So knowledge is one-hop, and "distributed knowledge
within a component" is *potential*, not actual. In the report say **one-hop
neighbourhood**, or the claim is simply false and easy to catch.

### Scope

| Spec | Where |
|---|---|
| `phi_reach`, `phi_live`, `phi_safe`, robustness, deadlock split | **Core.** C5 + C7 + C9 |
| `phi_fresh = G ( age_ij <= d )` | E2 only — vacuous under the C3 no-op channel |
| Assume-guarantee lemma | E6 |
| Rounds-to-agreement as time-to-mutual-knowledge | E5 |

---

## 4. GOTCHAS — things your LLM will confidently get wrong

These are all verified on our actual setup. An LLM's training data predates
POGEMA 2.0 and will give you outdated code.

1. **Install from GitHub, NOT PyPI.** `pip install pogema` gives a stale
   pre-2.0 version. Use:
   ```
   pip install git+https://github.com/Cognitive-AI-Systems/pogema.git
   ```
   Our version is `2.0.0a`. Check with `pogema.__version__`.

2. **`AnimationMonitor` does not exist.** It is `AnimationWrapper`. And
   `AnimationConfig` is not top-level — its kwargs go to `save_animation()`.

3. **Animation is off by default.** Call `env.enable_animation()` **before**
   `env.reset()`, or nothing is recorded and saving raises.

4. **`AStarAgent` needs dict observations.** Set
   `observation_type='POMAPF'` in `GridConfig`, or you get
   `IndexError: only integers, slices ... are valid indices`.

5. **COLLISIONS ARE IMPOSSIBLE.** Verified: two agents driven into each
   other in a corridor stop one cell apart and stay frozen forever. Do not
   write a collision counter — it reads zero. **Deadlock is the failure
   mode.** Any LLM that offers you a collision metric is wrong.

6. **Metrics are in `info[0]['metrics']`**, only the first agent's dict.
   The others just carry `{'is_active': bool}`.

7. **`GridConfig.MOVES` is a pydantic field, not a class attribute.**
   `GridConfig.MOVES` raises; `GridConfig().MOVES` works.

8. **Observation ≠ communication.** `obs_radius` is what a robot *senses*
   (a POGEMA setting). Communication is what it is *told* (our code). Keep
   them as separate dials; never let one drive the other.

9. **Don't build a telecom simulator.** A message is a small dataclass.
   Count messages. That is the whole communication-overhead metric.

10. **Don't install an STL library.** `rtamt` and friends will cost you a day of
    build pain for three formulas. The robustness definitions in §3.5 are about
    forty lines of plain Python over the trace. Write them yourself.

11. **Monitors run offline, never inside the loop.** They read the saved trace
    after the episode ends. The planner must never see a robustness value — if
    it did, the spec would be steering the thing it measures.

12. **Robustness sign convention: `>= 0` means satisfied.** `rho_reach` is a
    shortfall, so it is `<= 0` by construction and tops out at zero. Do not
    report its absolute value, and do not flip the sign halfway down the
    pipeline — a plot of `|rho|` looks exactly like a plot of `rho` and means
    the opposite.

### How to prompt your LLM

Paste, every time: **(a)** the interface block from §3, **(b)** the gotchas
above, **(c)** "POGEMA 2.0.0a, installed from GitHub, not the PyPI version",
**(d)** your step's pseudocode from §6, **(e)** §3.5 if your step touches specs
or robustness. Then ask for your module only. Do not ask it to design the
architecture — that is already decided.

---

## 5. When each person can start

```
Ronit    C1 ──> C2 ──> C3 ─────────────────────> E1, E2
Harsh              └──> C4 ──> C5 ─────────────> E3, E4
Dhanvi   C6 (independent, start now) ──────────> E5
Charitha C7 (independent, start now) ──────────> E6 (paper only)
Maanya                  C8 (needs C2) ─────────> E7
                              │
                    ═══ CHECKPOINT 1 ═══        (see §7)
```

### Ronit — C1, C2, C3 → E1, E2

**Start immediately. You are the critical path.**

Nothing blocks you. C1 is largely done. Three people are waiting on C2 and C3,
so ship them fast and plainly — stub implementations are fine.

Get the **interfaces in §3 frozen and pushed on day one**, before the
implementations are finished. Harsh and Maanya can then start against your
signatures while you are still writing the bodies.

Your extensions E1, E2 live inside your own C3, so no dependency there. But
Harsh's E3, E4 also live in C3 — coordinate, don't refactor it independently.

### Harsh — C4, C5 → E3, E4

**Needs: C2 and C3 from Ronit** (the interface signatures, not the finished
code).

You can start the A\* part immediately — it doesn't touch communication. Write
the planner's pathfinding first, then add the yield rule once Ronit's `Message`
class exists.

C5 falls out of C4: the yield rule and the deadlock condition are the same
logic seen two ways.

**C5 now includes the spec monitors (§3.5).** This is not extra scope, it is the
metric suite written as formulas — plus one addition, the epistemic split of each
deadlock into "the fact never arrived" and "it arrived and the rule stalled
anyway". You need the second number regardless, because it is how you find your
own bugs. Expose `blocking_neighbour()` from C4 so the monitors can use it.

**Two people depend on your yield rule** — Dhanvi's E5 instruments it, Charitha's
E6 proves things about it. Document how it works, or explain it to them directly.

Your E3, E4 live in Ronit's C3. Talk to him first.

### Dhanvi — C6 → E5

**No dependencies. Start immediately.**

LaCAM3 never touches our simulation loop — it takes a map plus start/goal pairs
and returns paths. Totally independent.

**Warning: this is the most likely two-day sinkhole in the project.** LaCAM3's
Python interface is on the `pybind` branch and needs a CMake build of C++17
code with recursive submodules. On Windows this can fight you. Fallbacks, in
order: (1) `pip install rt-lacam` from PyPI, which has working Python bindings;
(2) build the C++ binary and shell out to it, parsing `result.txt`.

E5 needs Harsh's yield rule instrumented with a counter. Ask him.

You also own the **synthesis** — see §2.

### Charitha — C7 → E6

**No dependencies. Start immediately.**

Build the harness against **fake data**. Generate random numbers in the shape
real results will have, build the whole sweep-and-plot pipeline on them, and
swap in real results later without changing a line.

**Your work determines whether anyone's numbers are usable.** Non-negotiables:
every run seeded and the seed recorded; configurations compared on *matched
instances* (identical map, starts, goals); raw results written to disk before
aggregation; error bars over ≥5 seeds. If these are missing, every result in the
project is unpublishable and nobody finds out until the end. Add one more: the
**raw trace of every run is saved**, not only the summary row, because the §3.5
monitors run offline and a reworded spec must not mean re-running the grid.

Your fake-data scaffolding should include the robustness columns
(`rho_reach_mean`, `rho_live_mean`, `pct_epistemic`) from the start, so the
plotting pipeline already has a second panel when Harsh's real numbers land.

E6 is a paper proof — no code, no dependencies, but ask Harsh how the yield rule
works first.

### Maanya — C8 → E7

**Needs: C2 from Ronit.** C8 extends his `CommunicationModel`.

You own the **headline experiment**. The range sweep is the direct answer to the
research question, and the graph statistics are what turn it from a description
("performance drops at r=3") into an explanation ("performance drops when the
communication graph fragments into more than four components").

The headline is **two panels**: success rate against range, and mean `rho_reach`
against range. The second is what makes "graceful degradation" a measured claim
rather than a word — and `n_components` is the epistemic bound (§3.5) that
explains both curves at once.

While waiting on C2, work out the k-NN-vs-range **matched mean degree**
comparison — for a fair comparison you need to pick *k* and *r* values that
produce the same mean degree, which takes some measurement.

E7 adds fields to Ronit's `Message` class. Tell him before you do.

---

## 6. Pseudocode per step

### C1 — Environment setup (Ronit)

Already largely done. Record answers in `ENVIRONMENT_CHECK_RESULTS.md`:

```python
# 1. Does 100 agents run, and how fast?
cfg = GridConfig(num_agents=100, size=64, density=0.3, seed=1,
                 obs_radius=3, max_episode_steps=256,
                 observation_type='POMAPF')
# time it

# 2. Collision behaviour — CONFIRMED IMPOSSIBLE. Keep the test as evidence.
#    Two agents, swapped goals, one corridor -> they freeze one cell apart.

# 3. What's in info after step()?  -> info[0]['metrics']
# 4. Can we inject per-agent actions?  -> yes, env.step([a0, a1, ...])
# 5. Does the same seed reproduce the same instance?  -> verify
```

### C2 — Communication layer (Ronit)

```python
class GlobalComm(CommunicationModel):
    def get_edges(self, positions):
        n = len(positions)
        return {i: [j for j in range(n) if j != i] for i in range(n)}

class NoComm(CommunicationModel):
    def get_edges(self, positions):
        return {i: [] for i in range(len(positions))}

# graph_stats — same implementation serves every topology
def graph_stats(self, edges):
    n = len(edges)
    degrees = [len(v) for v in edges.values()]
    # undirected view for components: union-find or networkx
    return {'mean_degree': sum(degrees) / n,
            'n_components': count_components(edges),
            'is_connected': count_components(edges) == 1}
```

### C3 — Channel interface (Ronit)

Genuinely a no-op. That is the point: it exists so E1–E4 need no refactor.

```python
class PerfectChannel(Channel):
    def deliver(self, messages, t):
        return messages          # everything arrives, unchanged
```

### Planner

**Implemented:** `planner.py` exports `IndependentAStar` and `DCMAPFPlanner`;
`pathfinding.py` supplies their shared deterministic A*. Both use the frozen
`Planner` interface and the existing runner. See README for a complete example.

```python
planner = DCMAPFPlanner(grid_map, goals, moves=env.unwrapped.grid_config.MOVES)
```

The borderless static obstacle map is known a priori (zero means free). Goals use
stable robot ID order. This assumption is fixed across topologies; global robot
state is never passed to `act()`. Own state arrives through `observe()`, and other
robots are known only through delivered messages. The start-relative observation
is never mistaken for a map-relative coordinate.

`observe()` prepares a static-map path **before** `compose()` broadcasts up to
three intended cells. A path step is removed only when the next observation
confirms movement; a simulator-rejected action leaves the step intact. Broadcasts
are snapshots of pre-coordination intentions, not promises of executed moves.
`reset()` clears paths, positions, timestamps and yield state between runs.

The local rule is deterministic, independent of inbox order:

1. If two robots claim an empty cell, the lower ID has priority; the other waits.
2. A currently occupied next cell blocks movement if its occupant stays or
   attempts a head-on swap. A claim to vacate elsewhere allows following.
3. On a swap, the lower-priority robot tries A* around received occupied/claimed
   cells. If that fails, breadth-first search finds the nearest refuge outside
   the head-on row or column; reaching it can require retreat along the corridor.
   Occupied cells and immediate claims from the inbox block the search. The peer's
   later advertised cells cannot be refuge destinations. Equal-length escapes
   use the shared row/column neighbour order. The refuge target persists across
   observations, including rejected moves. The robot waits there until a goal
   route opens or the peer leaves its inbox; there is no distance-based release.
   Avoidance never reads other robots' caches.
4. No inbox means independent A*. Only messages stamped with the current decision
   time affect coordination; a policy for delayed messages remains pending.

`has_priority(me, other)` defines the strict order. The pure helper
`blocking_neighbour(agent_id, position, next_cell, neighbours)` is shared by local
yielding and offline diagnostics. `intended_steps()` returns a copied mapping for
metrics instrumentation; it never feeds other robots' private state into decisions.

**Scope and limitation:** this is the guide's simplified A* plus local yield
baseline, with a local refuge search. It is not a verified reproduction of the
full Maoudj/Christensen algorithm, a complete MAPF solver, or a proof of deadlock
freedom. A no-passing corridor can remain blocked under perfect global messages;
multi-robot cycles and necessary long detours also need characterization. Do not
claim paper-level success rates or start C9 sweeps without investigating rule
failures on solvable cases. Dhanvi's E5 can instrument this rule; Charitha's E6
must account for occupancy, sidesteps, and graph assumptions explicitly.

### Metrics and monitors

**Implemented:** `metrics.py` records frozen `StepRecord` snapshots;
`monitors.py` evaluates all properties offline. Read the corrected §3.5 semantics.

```python
metrics = Metrics(goals, seed=seed, window=10,
                  intent_provider=planner.intended_steps)
result = run_episode(env, comm, channel, planner, metrics, max_steps)
raw_bundle = metrics.to_data()
# After saving/loading raw_bundle as JSON:
restored = Metrics.from_data(raw_bundle)
recomputed = restored.summary()
```

Existing `record(t, positions, graph_stats, arrived, inboxes)` and `summary()`
signatures are unchanged. The runner additionally calls optional
`capture_environment(infos)` after reset/step. This hook only copies POGEMA's
metrics from `infos[0]`; it does not evaluate specifications online and remains
compatible with old recorders that have no hook. Default finish-mode POGEMA
supplies ISR/CSR. `SumOfCostsAndMakespanMetric(env)` is optional: it supplies raw
cost values for comparison, while reported costs come from the trace.

**Verified exception to the original wrapper-only instruction:** the pinned
POGEMA cost wrapper clears an early robot's arrival time after it becomes inactive.
With arrivals at steps 1 and 4, it reports SoC 8 instead of 5; arrivals at 1, 3
and 6 give 18 instead of 10. For successful runs, `Metrics` reuses
`monitors.first_arrival()` and reports `SoC = sum(arrival_steps)` and
`makespan = max(arrival_steps)`. A robot initially at its goal has arrival step
zero. Raw wrapper results remain unchanged in `environment_metrics`; they are
not used as the standard cost metrics. Summary and raw bundles carry
`cost_definition="first_arrival_steps_v1"`. A successful CSR without every
recorded arrival raises an error rather than yielding a misleading cost.

**Bounded-run convention:** use `max_steps == config.max_episode_steps` so an
unsolved run ends at POGEMA's own timeout and produces its terminal metrics. If
our caller cuts off earlier (including zero steps), built-in metrics are unknown
and returned as `None`; `n_arrived` and trace robustness are still available.
Makespan and SoC are `None` for unsolved runs, for aggregation over solved
instances only. The raw `environment_metrics` dictionary retains the wrapper's
original timeout values. Always report success alongside solved-only costs.

**Blocker evidence:** `StepRecord` is unchanged. Its positions/inbox IDs alone
cannot identify a planned conflict. With `intent_provider`, the recorder captures
pre-decision `{agent_id: next_cell}` mappings in `intents[t]`. After the run,
`deadlock_causes(trace, goals, W, intents=...)` reconstructs potential blockers
using the planner's helper and looks for their IDs in the inbox at the
earliest violating window's start. Absent intentions or no identifiable blocker yield `unattributed`.
These labels are diagnostic proxies, not a causal proof. No experiment may
silently discard unattributed stalls or declare every missing inbox the cause.

The summary includes seed, agent count, executed steps, window, liveness and
cost definitions, ISR/CSR, solved-only costs, `n_arrived`, counts for all three deadlock
labels, per-run mean reach/liveness robustness, the number of agents with
evaluated liveness, safety margin, delivered messages, and mean graph statistics.
`pct_epistemic` is the fraction among **attributed** stalls (not a percentage),
or `None` when none are attributed. `rho_safe` is `None` when no active pair exists.
The summary's `deadlock_causes` uses string robot-ID keys so saved JSON summaries
compare directly with recomputed summaries; monitor functions use integer IDs.

Message rate is delivered transmissions / (initial fleet size × executed steps),
zero for a zero-step run. Means of degree and component count exclude the terminal
row, which has no decision or transmissions. Finished robots remain in position
rows but are excluded from safety and future liveness requirements. The single
liveness evaluator drives stall detection; there is no second displacement test.

**C7 handoff:** `summary()` contains scalar/nested results, while `to_data()`
contains goals, seed, window, semantic version, frozen rows, intention sidecar,
and raw environment metrics. Intentions contain decision rows only; the terminal
row has no broadcast and is excluded from `metrics.intents` and exported data.
Persist **both** under `outputs/` before aggregation.
`Metrics.from_data()` handles JSON's string keys and supports offline recomputation
without POGEMA or a planner. Older raw bundles without a cost-definition field
can still be loaded; summaries are recomputed using first arrivals, and stale
terminal intention entries are ignored. Regenerate old summary rows before using
them in cost comparisons. A saved frozen trace alone can evaluate reach/live/safe
but cannot reproduce blocker attribution. Serialization/file orchestration,
matched instances, oracle ratios and statistical plots remain C6/C7/C9 work.

### C6 — Oracle & floor (Dhanvi)

**Implemented:** `decentralized_mapf/oracle/` uses the executable fallback;
see README for binary setup. The oracle is independent of `run_episode()`.

```python
from decentralized_mapf.oracle import oracle_solve, oracle_metrics, oracle_soc_ratio

paths = oracle_solve(grid_map, starts, goals, timeout=30)
if paths is not None:
    reference = oracle_metrics(paths)
    ratio = oracle_soc_ratio(decentralized_soc, reference["SoC"])
```

The parser retains the entire solver timeline, including goal departures,
revisits, and terminal waits. `validate_paths()` checks that original trajectory's
starts, final goals, legal moves, vertex collisions, and edge swaps. Never cut
paths at their first goal visit before validation: that can create an artificial
stationary blocker or hide an invalid later move.

For reporting, `oracle_metrics()` infers each fixed goal from the path endpoint
and uses its **first** occurrence. The default transition convention reports
`makespan = max(first_arrivals)` and `SoC = sum(first_arrivals)`, matching the
project's `first_arrival_steps_v1` costs. Initial-goal arrivals cost zero; waits
before arrival count. The optional `positions` convention adds one initial sample
per robot. Neither convention mutates or truncates paths. Public oracle call
signatures and returned metric keys remain unchanged.

These comparison costs can differ from LaCAM3's native stay-at-goal objective
when a robot leaves a visited goal. Its optimization is not a proof of optimality
under POGEMA's disappear-on-finish semantics. Keep full paths for replay and
validation; do not interpret their common length as each robot's cost. Regression
tests cover staggered arrivals, goal revisits through a side pocket, and invalid
movement after a goal visit. The no-communication floor uses the same decentralized
planner with `NoCommunication`; compare costs only for solved runs and handle a
zero oracle SoC explicitly, as `oracle_soc_ratio` rejects that undefined ratio.

### C7 — Experiment harness (Charitha)

The following is orchestration pseudocode, not an implemented harness. C7 owns
instance/environment construction (`make_instance`/`build_run`) and file helpers.
`build_run` must supply a seeded finish-mode environment. The native cost
wrapper is optional and used only for raw diagnostic comparisons. Use the
actual planner and recorder calls below; summaries do not contain a `trace` key.

```python
# configs live in YAML, NOT in the script
# experiments/range_sweep.yaml:
#   topology: [global, none, range_2, range_5, knn_3]
#   num_agents: [10, 25, 50, 100]
#   map: [random_32, warehouse, maze]
#   seeds: [1,2,3,4,5]

def run_sweep(config_path, out_dir):
    cfg = yaml.safe_load(open(config_path))
    rows = []
    for topo, n, map_name, seed in itertools.product(*cfg.values()):
        # MATCHED INSTANCES: identical map/starts/goals across topologies.
        # The seed must fix the INSTANCE, independently of the topology.
        instance = make_instance(map_name, n, seed)
        env, comm, planner = build_run(instance, topo)
        metrics = Metrics(planner.goals, seed=seed,
                          intent_provider=planner.intended_steps)
        try:
            result = run_episode(env, comm, PerfectChannel(), planner, metrics,
                                 max_steps=env.unwrapped.grid_config.max_episode_steps)
        finally:
            env.close()
        # Persist raw evidence before CSV aggregation, including intentions.
        save_json(f"{out_dir}/traces/{topo}_{n}_{map_name}_{seed}.json",
                  {'summary': result, 'raw': metrics.to_data()})
        scalars = {key: value for key, value in result.items()
                   if not isinstance(value, dict)}
        rows.append({'topology': topo, 'n_agents': n, 'map': map_name,
                     'seed': seed, **scalars})
        # result already carries rho_reach_mean, rho_live_mean, pct_epistemic
        # write incrementally — do not lose 3 hours to a crash at row 900
        append_csv(f"{out_dir}/raw.csv", rows[-1])
    return pd.DataFrame(rows)

def plot_with_errorbars(df, x, y, hue):
    g = df.groupby([hue, x])[y].agg(['mean', 'std', 'count'])
    g['sem'] = g['std'] / g['count'] ** 0.5
    # plot mean with yerr=sem, one line per hue
```

Runs are embarrassingly parallel — `multiprocessing.Pool` over configs makes
the whole grid a few minutes. Worth doing early.

**Persist the trace per run, not just the summary row.** The §3.5 monitors are
offline, so if a specification is reworded — a different `W`, a stricter
liveness window — you re-evaluate the saved traces in seconds instead of
re-running the grid. This is rule 3 applied to specs, and it is the only reason
changing a formula late is survivable.

`rho_reach_mean` gets its own plot beside every success-rate plot. Same x-axis,
same hue, same error bars. Two panels, not two figures.

### C8 — Range & k-NN topologies + graph stats (Maanya)

**Implementation available:** `RangeCommunication` and `KNNCommunication` live
in `decentralized_mapf/communication.py` and are exported from the package. Use
these implementations rather than copying the earlier topology pseudocode:

```python
from decentralized_mapf import RangeCommunication, KNNCommunication

comm = RangeCommunication(r=3)  # Or KNNCommunication(k=2).
edges = comm.get_edges(positions)
stats = comm.graph_stats(edges)
```

`positions[i]` identifies robot i. Every robot is a key, including isolated ones;
there are no self-links. Both models are deterministic and use Manhattan distance.
Range accepts nonnegative numeric `r` (including `float("inf")` for global range),
includes the distance boundary, and produces symmetric links. k-NN accepts a
nonnegative integer `k`, selects at most the other available robots, breaks equal
distances by robot ID, and can produce asymmetric links. `k=0` gives no links.

Both models reuse the existing `graph_stats` helper: `mean_degree` is mean outgoing
degree; `n_components` and `is_connected` describe the undirected view, including
isolated keys. No frozen method signatures or additional dependencies were added.
`tests/test_topologies.py` covers the topology rules and parameter boundaries;
run the full test suite using the README's validation command.

**Active-robot integration:** the runner passes only active positions to the
topology, preserving original ID order, then maps local graph indices back to
stable IDs. This selects up to `min(k, n_active - 1)` neighbours without allowing
finished robots to consume slots, and preserves original-ID tie-breaking. For
example, with positions `[(0, 0), (0, 1), (0, 10)]`, robot 1 finished, and k=1,
the routed graph is `{0: [2], 2: [0]}`. Topology implementations treat their input
indices as local; the runner owns the ID mapping. Regression tests in
`tests/test_runner.py` cover reselection after arrival, original IDs, ties, and
empty/single-active graphs across the core topologies.

**Matched mean degree.** To claim "structure matters, not just quantity", the
k-NN and range conditions must be compared at equal mean degree. Measure it:
run a few episodes per setting, record `mean_degree`, then pick the (r, k) pairs
that line up. Do this before the main sweep.

The topology implementations alone do not complete the range/performance curves,
matched-degree comparison, robustness plots, or message-content extension. Those
still need C6/C7/C9 integration and validation; the modules now supply the planner and
recorder/monitors described above. Keep
generated traces/results under `outputs/` and complete core validation first.

### E1 — Packet loss (Ronit)

```python
class LossyChannel(Channel):
    def __init__(self, p, rng): self.p, self.rng = p, rng

    def deliver(self, messages, t):
        return [m for m in messages if self.rng.random() > self.p]
```

Sweep `p ∈ {0, 0.1, 0.2, 0.4, 0.6, 0.8}`. The interesting question is the
**shape** — graceful slope or a cliff. A cliff is the better finding.

Use a dedicated `rng` seeded from the run seed, so loss patterns are
reproducible.

### E2 — Message delay (Ronit)

```python
class DelayedChannel(Channel):
    def __init__(self, d):
        self.d, self.queue = d, []

    def deliver(self, messages, t):
        self.queue.extend((t + self.d, m) for m in messages)
        due = [m for (arrive, m) in self.queue if arrive <= t]
        self.queue = [(a, m) for (a, m) in self.queue if a > t]
        return due

    def reset(self): self.queue = []
```

**The hardest extension.** Robots now act on stale positions, so planner bugs
become hard to diagnose. Test with `d=1` on two agents before scaling up.

This is the one condition where `phi_fresh = G ( age_ij <= d )` is not vacuous.
`StepRecord.max_age` already carries the signal, so monitoring it costs one
line — and it doubles as a test that `DelayedChannel` does what it claims.

### E3 — Disconnection (Harsh)

```python
class BlackoutChannel(Channel):
    """Each robot goes comms-dark for windows of W steps."""
    def __init__(self, window, prob, rng, n_agents):
        self.dark_until = {i: -1 for i in range(n_agents)}

    def deliver(self, messages, t):
        for i in self.dark_until:
            if t > self.dark_until[i] and self.rng.random() < self.prob:
                self.dark_until[i] = t + self.window
        return [m for m in messages if t > self.dark_until[m.sender]]
```

Note this is nearly E1 with `p=1` for a window — say so in the write-up, it is
an honest observation rather than a weakness.

### E4 — Agent failure (Harsh)

Not a channel effect. The robot stops moving and becomes an obstacle.

```python
class FailureInjector:
    def __init__(self, fail_frac, rng, n_agents, max_steps):
        self.failed = {}    # agent_id -> step it failed at

    def override_actions(self, actions, t):
        for i in self.pick_new_failures(t):
            self.failed[i] = t
        for i in self.failed:
            actions[i] = WAIT        # frozen; other robots must route around
        return actions
```

Exclude failed robots from the success-rate denominator, and say so.

### E5 — Consensus framing (Dhanvi)

No new algorithm — instrument Harsh's existing yield rule. The authoritative
[E5 measurement contract](E5_CONSENSUS_CONTRACT.md) fixes the definition and
implementation acceptance criteria. Instrumentation remains pending.

One round is one nonterminal runner timestep. Agreement means the first round
of a pair's conflict episode where both agents receive each other's
**current-round pre-decision claims**. Report this as **time to mutual claim
receipt**, an operational measure of §3.5's time-to-mutual-knowledge framing.
It is not an ACK protocol, common knowledge, or physical conflict clearance.
Elapsed rounds are `t_agreement - t_start`; same-round receipt is 0.

The old conflict-detected/resolved sketch conflated receipt with clearance and
overwrote the start on repeated detection. Follow the linked contract instead:
detect pairwise conflicts independently of delivery, preserve episode starts,
count each agreement once, and report missing agreements and coverage alongside
successful-sample mean/max. Plot these against communication quality (range,
loss rate), with the operational definition stated in the report. Keep the
planner, messages, frozen interfaces, and observation settings unchanged.

### E6 — Deadlock-freedom proof (Charitha)

**Planner counterexample to the old sketch:** a robot can be blocked by another robot
even when it never yields. Perfect knowledge and a total priority order alone do
not imply that the highest-priority robot advances. The no-passing corridor in
`tests/test_planner_integration.py` remains stalled with global messages. Treat the
following as an unproved proposal, not a guarantee; any valid lemma needs stronger
map/feasibility/escape assumptions and must model the actual local rule.

Paper, not code. One lemma, roughly ten hours.

```
Claim, as an assume-guarantee statement in the §3.5 notation:

    ( topology == global )  AND  G ( age_ij <= d )   ==>   G ( NOT deadlock )

i.e. under global communication and message delay bounded by d,
     the yield rule cannot produce permanent deadlock.

Sketch:
  1. Priority is a strict total order on agents (deterministic,
     antisymmetric — see C4). Call the highest-priority agent among
     any conflicting set a*.
  2. a* never yields, since every conflicting agent has lower priority.
  3. Therefore a* advances along its path every step it is not blocked
     by a static obstacle.
  4. With delay <= d, a*'s claim is known to all conflicting agents
     within d steps, so they yield within d steps.
  5. Induction on the priority order: once a* reaches its goal it
     leaves the conflict set; apply (1)-(4) to the remainder.
  => no cycle of mutual waiting persists. []
```

State assumptions explicitly, and note where they fail. Packet loss breaks
step 4, which is exactly why E1's empirical result matters: E1 falsifies the
antecedent, and the curve then shows what happens outside the guarantee. The
second conjunct of the antecedent is literally the E2 freshness spec
`phi_fresh = G ( age_ij <= d )`, monitorable from `StepRecord.max_age`, so if E2
ships you can **check the assumption held on every run you cite** instead of
asserting it. Template to
follow: *Provably Safe Multi-Robot Coordination With Unreliable
Communication*, IEEE RA-L.

### E7 — Message-content ablation (Maanya)

```python
# three message variants, same topology and channel
CONTENT_LEVELS = {
    'position_only': lambda m: Message(m.sender, m.position, None, [], m.sent_at),
    'position_goal': lambda m: Message(m.sender, m.position, m.goal, [], m.sent_at),
    'full_path':     lambda m: m,     # includes next_cells
}
```

Report performance against **bytes per robot per step**, not just message count
— that is the whole point of the ablation. Prices information against bandwidth.

---

## 7. Integration checkpoints

Two moments where everything must work together. Do not skip either.

### Checkpoint 1 — the three-bar plot

**Needs:** C2 + C4 + C5 + C6 + C7. **Owners:** Ronit + Harsh, with Dhanvi and
Charitha supplying oracle and harness.

One plot. Ten agents. Three bars with error bars: **oracle**, **global
communication**, **no communication** — in that order, descending.

If the bars come out in that order, the entire pipeline is validated and
everything afterwards is turning dials. If they do not, there is a bug, and you
find it now rather than in the final week.

**Plot mean `rho_reach` as a second panel, same three bars.** It should order the
same way. If success rate orders correctly and robustness does not, the bug is in
the monitor, not the pipeline — which is exactly what you want to learn here
rather than the night before the report. Check `rho_safe >= 0` on the same runs
while you are at it; it confirms gotcha 5 still holds in our loop.

**Nobody starts their extension work before this plot exists.** The temptation
is to skip the boring validation and go straight to interesting topologies.
Teams that do this discover in the final week that the oracle was misconfigured
the whole time.

### Checkpoint 2 — core complete

**Needs:** C8 done and the core sweeps run.

From here the project is deliverable in full even if every extension fails.
Treat this as the real deadline. Extensions start only after it.

---

## 8. Rules

1. **Everything takes a seed.** Every run, every plot, every number, and the
   seed is recorded in the results row. Unseeded results are unreproducible and
   an anomalous curve will be undebuggable.
2. **Interfaces frozen after Ronit pushes them.** Changing a signature later
   costs four people their week.
3. **Raw results to disk before aggregating.** Plots must be regenerable
   without re-running anything.
4. **Configs in YAML, not in scripts.**
5. **Observation and communication stay separate dials.**
6. **Core before extensions, always.**
7. **No new features once the core sweeps start.** Runs, plots and prose only.
8. **Specifications are written down before the sweeps run**, not after seeing
   the curves. A spec tuned to the data proves nothing, and it is the first
   thing the professor will ask about.
9. **Specs are evaluated offline, on the saved trace.** No monitor inside the
   simulation loop, and no robustness value ever visible to the planner.
