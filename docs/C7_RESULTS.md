# C7 results

What the core sweeps show, experiment by experiment. Design and definitions are
in [EXPERIMENTS.md](EXPERIMENTS.md). All runs use the perfect channel and the
team's `DCMAPFPlanner`. Numbers are means over instances with 95% bootstrap
intervals; "pp" means percentage points. Every run passed every invariant in
`analysis.check_invariants` (2,500 runs, 0 errors).

Each config's figures are in `outputs/experiments/<config>/figures/` after running
`plot_results.py`; tables are in `summary.csv` and `paired.csv`.

## Summary

1. Communication matters. Without it, success falls sharply, and it falls further
   as robots meet more often.
2. Very little communication is enough at moderate density. Hearing robots one
   cell away (range 1) matches global communication on random and warehouse maps,
   while delivering about 25 times fewer messages.
3. The reason is geometric: a blocker is always within distance 2, and range 1
   already hears every blocker that occupies the claimed cell. The remaining
   contests over empty cells are settled by the simulator's collision rule.
4. Structure matters at equal degree: k-NN with k = 1 is clearly worse than range 1,
   because k-NN links are directed and miss blockers sitting in the claimed cell.
5. Under heavy congestion (128 robots on 32 × 32), global beats local communication
   by 4–11 pp. At constant density it does not.
6. With communication, almost all remaining stalls are "heard, still stuck":
   the limit is then the planner rule and the map, not information.

7. LaCAM3 solved every instance up to 100 robots. The decentralized planner falls
   further behind as the fleet grows: at 100 robots global brings 30–64% of
   robots home, and on solved instances its extra cost rises from about 2%
   (10 robots) to 18–22% (50 robots).

## E1 — Does communication help at all? (`ladder`)

**Question.** Does global communication beat no communication on the same instances?

**Setup.** N = 10 on 32 × 32 random, warehouse and maze maps, 20 seeds each.
Global vs none. The oracle run (`outputs/experiments/ladder_oracle`) repeats
the same 60 instances with LaCAM3 built from source on Linux (30 s limit per
instance); its decentralized runs are identical to the first ladder run.

**Metrics.** CSR, ISR, ρ_reach, SoC on instances both settings solved, and the
SoC ratio $SoC_{\text{ours}} / SoC_{\text{LaCAM3}}$ on instances we solved.

**Result.**

| Map | CSR global | CSR none | ISR global | ISR none | ISR global − none (paired) | higher / equal / lower |
|---|---|---|---|---|---|---|
| random | 95% | 40% | 97.5% | 77.5% | +20.0 pp [11.5, 29.5] | 11 / 9 / 0 |
| warehouse | 100% | 40% | 100% | 84.0% | +16.0 pp [9.5, 23.0] | 12 / 8 / 0 |
| maze | 100% | 15% | 100% | 65.5% | +34.5 pp [25.5, 43.5] | 17 / 3 / 0 |

- Global was never worse than none on any of the 60 instances.
- Mean ρ_reach: none −3.3, −2.7, −5.1 cells; global −0.4, 0, 0. Without messages,
  failed robots stop several cells from their goals.
- On the 19 instances both settings solved, the trajectories were **identical**
  (checked step by step), so the SoC difference is exactly 0.
- Arrival curves flatten by about step 75 of 256. Robots that have not arrived
  by then never do.
- LaCAM3 solved all 60 instances. SoC ratio: global 1.043 [1.030, 1.060] over
  59 solved instances; none 1.002 [0.998, 1.005] over its 19. The none ratio is
  low only because it solves the easy instances, where global's runs are the
  same trajectories. Global's extra cost comes from instances none never solves.
- The single global failure (random, seed 2) is four robots meeting head-on in a
  one-cell corridor with no side pocket. All four hear each other; it is
  labelled a rule failure. `plot_episode.py --map random --n-agents 10 --seed 2`
  shows the same jam under global, range 1 and none.

**Interpretation.** Messages change behaviour only when a robot is blocked; on
instances where nobody blocks anybody the two settings are the same run. When
robots do block each other, no communication tends to leave them stuck for good.

**Limits.** At N = 10 conflicts are rare, so this shows that communication
matters, not how much is needed. LaCAM3 is a near-optimal reference: it plans
for robots that stay on their goals, while POGEMA removes them, so a ratio
slightly below 1 is possible. Larger fleets are in the next section.

## E1, extended — Distance from the centralized planner as the fleet grows (`oracle`)

**Question.** How far is decentralized coordination from LaCAM3, and how does
that gap change with N?

**Setup.** N ∈ {10, 25, 50, 100} on 32 × 32 random, warehouse and maze maps,
10 seeds each (120 instances). none, range 2 and global on the same instances;
LaCAM3 with a 10 s limit per instance.

**Metrics.** ISR; SoC ratio $SoC_{\text{ours}} / SoC_{\text{LaCAM3}}$ on instances
the setting fully solved (number of such instances in brackets).

**Result.** LaCAM3 solved all 120 instances.

| Map | N | ISR none | ISR range 2 | ISR global | ratio range 2 | ratio global |
|---|---|---|---|---|---|---|
| random | 10 | 82.0% | 95.0% | 95.0% | 1.018 (9) | 1.018 (9) |
| random | 25 | 54.8% | 95.2% | 97.2% | 1.059 (7) | 1.095 (8) |
| random | 50 | 33.0% | 82.0% | 88.4% | 1.116 (3) | 1.181 (5) |
| random | 100 | 12.8% | 50.6% | 63.7% | – | – |
| warehouse | 10 | 83.0% | 100% | 100% | 1.016 (10) | 1.019 (10) |
| warehouse | 25 | 56.8% | 95.6% | 97.2% | 1.056 (7) | 1.094 (8) |
| warehouse | 50 | 35.0% | 82.0% | 86.8% | 1.135 (3) | 1.222 (2) |
| warehouse | 100 | 17.8% | 47.8% | 55.0% | – | – |
| maze | 10 | 73.0% | 100% | 100% | 1.046 (10) | 1.053 (10) |
| maze | 25 | 35.2% | 70.0% | 77.6% | 1.090 (1) | 1.364 (2) |
| maze | 50 | 21.2% | 48.4% | 52.8% | – | – |
| maze | 100 | 9.2% | 23.7% | 29.7% | – | – |

– means no instance was fully solved, so no ratio exists.

- The gap in ISR to LaCAM3 (100%) widens with N for every setting.
- Communication keeps a large lead over none at every N (random, 50 robots:
  88.4% global vs 33.0% none).
- On solved instances the cost ratio grows with N: about 1.02 at 10 robots,
  1.06–1.10 at 25 and 1.12–1.22 at 50.
- none's ratio at N = 10 is about 1.00 (0.997 on random). It solves only easy
  instances, and a value just below 1 is possible because LaCAM3 keeps robots
  on their goals while POGEMA removes them.

**Interpretation.** With few robots the decentralized planner is close to the
centralized one, in both success and cost. Crowding is what separates them:
local yielding resolves fewer conflicts as robots meet more often, and the
conflicts it does resolve cost more waiting.

**Limits.** Ratios compare each setting on its own solved instances, so global's
higher ratio partly reflects that it solves harder instances than range 2; it is
not evidence that global plans worse. Cells with 1–3 solved instances (maze 25,
the 50-robot rows) are too few to trust. LaCAM3 is a near-optimal reference
under stay-at-goal semantics, not a proven optimum for POGEMA's rules.

## E2 — How far must messages carry? (`topology`)

**Question.** How does success change with communication range r?

**Setup.** N = 50, 32 × 32, three maps, 20 seeds. none, range r ∈ {1, 2, 3, 5, 8, 16}, global.

**Metrics.** ISR, ρ_reach, share of conflicts whose blocker was heard.

**Result.**

| Map | none | r = 1 | r = 2 | r = 16 | global | r = 1 − global (paired) |
|---|---|---|---|---|---|---|
| random | 32.8% | 86.1% | 84.9% | 87.8% | 87.5% | −1.4 pp [−5.4, +2.5] |
| warehouse | 37.9% | 85.5% | 82.8% | 86.8% | 86.9% | −1.4 pp [−4.1, +1.4] |
| maze | 19.6% | 47.9% | 45.9% | 49.5% | 52.5% | −4.6 pp [−9.6, +0.1] |

- Going from none to r = 1 adds about 50 pp. Going from r = 1 to global adds
  nothing distinguishable on random and warehouse, and about 5 pp on maze.
- Every r ≥ 2 delivered 100% of blockers' claims, as derived in EXPERIMENTS.md §2;
  the invariant checker confirmed it on every run. r = 1 delivered 49%, 46% and 36%.
- On 8 random instances, all 2,073 distance-1 blockers were heard under r = 1, and
  all 4,288 unheard ones were at distance 2 (contests). In 3,052 of those the robot
  stepped forward and the simulator refused the move, which ends where a heard
  "wait" would have.

**Interpretation.** For this planner, the information that matters is local.
Range 1 carries the conflicts the simulator cannot settle (a robot sitting in the
claimed cell). Contests over an empty cell get settled anyway, by POGEMA's
priority collision rule, at the cost of a refused move.

**Limits.** This depends on POGEMA's collision semantics; a simulator that let
contests deadlock would make r = 2 necessary. The maze gap to global is small and
its interval touches zero for r = 1.

## E3 — Does the structure of the talk graph matter? (`topology`)

**Question.** At the same mean degree, do range and k-NN perform the same?

**Setup.** Same runs; k ∈ {1, 2, 3, 4, 8}. Settings are compared at their measured
mean degree, not their parameter.

**Result.**

- At degree ≈ 1: range 1 gives 86.1% ISR on random, k-NN 1 gives 75.2%.
  k-NN 1 vs global: −12.3 pp [−17.5, −7.1] random, −8.5 [−12.7, −4.8] warehouse,
  −10.7 [−15.2, −6.0] maze.
- k-NN 1 heard only 28%, 37% and 26% of blockers. In 8 instances it missed
  2,721 blockers at distance 1, robots sitting in the claimed cell.
- From k = 2 upward, k-NN and range lie within each other's intervals at equal degree.

**Interpretation.** k-NN links are directed: robot i hears j only if i is among
*j's* nearest robots. A robot in i's way may have chosen a different neighbour,
so i never hears it. Range links are symmetric. At very low degree this
difference decides who hears the blocker.

**Limits.** Mean degree counts potential receivers among active robots, averaged
over steps; it is a summary of the graph, not of who needed whom.

## E5 — Message load vs success (`topology`)

**Question.** Do more messages buy more success?

**Result.** Delivered messages per robot per step: range 1 ≈ 0.3 (random,
warehouse), global 8.4 and 5.8. Global sends 20–27× more for an ISR difference
that is not distinguishable from zero on those maps. Past the first fraction of a
message per robot per step, the curve is flat.

Stalls by cause (per instance): with none, 22 / 23 / 20 epistemic (random,
warehouse, maze). With any r ≥ 2 the epistemic count is 0. The rest are "heard,
still stuck" (about 3–5 per instance on random and warehouse, 10–11 on maze for r ≥ 2)
plus unattributed stalls.

**Interpretation.** Communication removes the stalls caused by missing
information; the remaining stalls come from the yield rule meeting tight
geometry. More messages cannot fix those.

**Limits.** Stall labels are diagnostics from the blocking rule, not causal
proofs; "unattributed" (no blocker identified) is large in the maze.

## E4 — How does the system scale? (`scaling_congestion`, `scaling_density`)

**Question.** How does success change with fleet size, and is it crowding or size?

**Setup.** N ∈ {8, 16, 32, 64, 128}; none, range 2, k-NN 2, global; random and
warehouse; 20 seeds. Congestion: fixed 32 × 32. Density: map side 16 → 64, about
0.03 robots per cell, step limit 8 × side.

**Result (ISR at N = 8 → 128).**

| Map | Setting | Congestion | Density |
|---|---|---|---|
| random | none | 84 → 11% | 74 → 21% |
| random | range 2 | 97 → 39% | 100 → 87% |
| random | global | 97 → 50% | 100 → 88% |
| warehouse | none | 92 → 12% | 89 → 25% |
| warehouse | range 2 | 100 → 40% | 98 → 80% |
| warehouse | global | 100 → 44% | 98 → 83% |

- Up to N = 16, range 2, k-NN 2 and global gave identical ISR on every instance.
- Congestion, N = 128: range 2 − global = −11.0 pp [−14.7, −7.4] random
  (global higher on 19 of 20), −4.4 pp [−8.7, −0.2] warehouse.
- Density, N = 128: −1.8 pp [−4.6, +1.2] random, −2.5 pp [−5.7, +0.3] warehouse.
- Message load at constant density: range 2 stays about 0.2–0.7 per robot per step;
  global grows with N.
- At N = 128 (congestion, random), range 2 had 89 refused moves per robot, global 67.

**Interpretation.** Most of the drop with N comes from crowding: at constant
density, communicating fleets keep 80–88% ISR at 128 robots. Without
communication, success still falls at constant density, because on a larger map
each robot travels further and meets more robots.

Global's advantage appears only when crowded. A possible mechanism, **not
verified**: a yielding robot holds its refuge until its peer leaves its inbox.
Under range 2 the peer "leaves" once it is 3 cells away, possibly before the
conflict is over. Testing this needs the planner's yield state recorded per step.

**Limits.** ρ_reach is in grid cells, so its scale grows with the map in the
density sweep. Delay covers arrived robots only: global's larger delay at large
N partly reflects that more of its robots arrive after long waits, so it is not
an efficiency comparison.

## Cross-cutting checks and critique

- **Matched instances.** All topologies of a seed had the same instance id; no two
  seeds shared one. A CSV parsing bug that merged two hex ids was found by a
  missing pair and fixed; an invariant now guards it.
- **Step limit.** Of 1,601 unsolved runs, one had any arrival in the last quarter
  of its step limit. Unfinished robots are stuck, so the limit does not bias ISR.
- **Costs.** SoC and makespan are compared only on instances solved by every
  compared setting. At N = 50, CSR is low (maze 0%), so cost comparisons there are
  not meaningful and are not made.
- **Seeds.** 20 paired instances per cell give intervals of a few pp for ISR. CSR
  intervals are wide (±20 pp); CSR differences are not claimed.
- **Maps.** Three synthetic map types at one obstacle density. Results on
  benchmark maps may differ, especially for the maze, which is unusually hostile.
- **Runtime.** Global is much slower to *simulate* (N = 128: 26 s vs 3 s per run),
  mostly because the runner copies one message per receiver. This is a cost of
  the simulation, not a measurement of a real network.
- **Not studied here.** Message loss and delay, agent failure, and E5 receipt
  timing (disabled by its contract in core sweeps).

## What this does not show

- No guarantee: the planner still deadlocks in no-passing corridors with perfect
  global information.
- No optimality claim: LaCAM3 is a near-optimal reference under stay-at-goal
  semantics, not a proven optimum for POGEMA's rules.
- No generalization beyond this planner, these maps and POGEMA's priority collisions.
