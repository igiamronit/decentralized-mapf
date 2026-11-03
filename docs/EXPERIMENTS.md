# C7 experiment harness

This file explains what the harness does, why the experiments are designed the
way they are, how to run them, and how to read the outputs. Results and their
interpretation are in [C7_RESULTS.md](C7_RESULTS.md).

## 1. What the harness does

For each experiment config it:

1. builds every problem instance once,
2. runs every communication setting on each instance,
3. writes one result row per run, including failures,
4. checks the rows against invariants, summarizes them over instances, and plots them.

It reuses the project modules. Nothing in the planner, runner, metrics or
monitors was changed.

```text
config.yaml -> make_instance -> build_run -> run_episode (planner, topology, PerfectChannel, Metrics)
            -> summary + coordination analysis -> results.csv -> analyze.py / plot_results.py
```

## 2. Design

### Matched instances

An instance is the tuple

$$(G,\ N,\ \{s_i\},\ \{g_i\})$$

— grid, robot count, starts and goals. It is fixed by `(map type, map size, N, seed)`
and built once by `make_instance`, before any topology runs. Every topology then
receives the same instance, so a difference between two settings on one instance
comes only from communication.

This is checked, not assumed:

- every row stores an `instance_id`, a hash of the grid, starts and goals;
- `run_one` checks that the environment's starts and goals equal the instance's;
- `check_invariants` checks that all topologies of one seed share one id, and that
  different seeds never share one.

### The experimental unit

Robots in one episode share a map and block each other, so they are not
independent samples. The unit is the instance: every mean, interval and paired
difference uses one value per instance.

### Experiments and the question each answers

| Config | Question | Varied | Fixed |
|---|---|---|---|
| `ladder` (E1) | Does communication help at all? How far from the centralized reference? | global vs none (+ oracle) | N = 10, 3 maps, 20 seeds |
| `topology` (E2, E3, E5) | How much range or how many neighbours is enough? Does graph structure matter at equal degree? How does message load relate to success? | none, range r ∈ {1,2,3,5,8,16}, k-NN k ∈ {1,2,3,4,8}, global | N = 50, 32 × 32, 3 maps, 20 seeds |
| `scaling_congestion` (E4a) | What happens as robots are added to the same space? | N ∈ {8,16,32,64,128} | 32 × 32 map |
| `scaling_density` (E4b) | What happens at larger scale but similar crowding? | N and map side together | ≈ 0.03 robots per cell |
| `oracle` (E1, extended) | How far from the centralized reference as the fleet grows? | N ∈ {10, 25, 50, 100}; none, range 2, global, LaCAM3 | 32 × 32, 3 maps, 10 seeds, 10 s oracle limit |
| `smoke` | Does the pipeline run? | — | 2 seeds; never evidence |

Range sweep and topology comparison use the same runs, so there is one config,
not two.

### Choosing r and k

Two facts decide which values are worth running.

**A blocker is always within distance 2.** By the team's blocking rule, robot j
blocks robot i's claimed cell q in one of two ways:

- j occupies q, so $d(p_i, p_j) = d(p_i, q) = 1$;
- j claims q while q is empty, so $d(p_i, p_j) \le d(p_i, q) + d(q, p_j) = 2$.

In the second case the distance is exactly 2. On a four-connected grid two
adjacent cells cannot share a neighbour (the grid is bipartite), so two robots
at distance 1 cannot both claim the same third cell. So:

- range r ≥ 2 delivers every blocker's claim (under a perfect channel);
- range 1 delivers every blocker that *occupies* the claimed cell, and no blocker
  that only *contests* an empty cell.

This is a statement about delivery, not about resolving the conflict. The
invariant checker verifies it on every run.

**When a setting equals global.** Range r ≥ 2(size − 1) reaches every cell of the
map, and k ≥ N − 1 links every robot. Such settings duplicate global. The harness
prints a note for them. All chosen values stay far from these limits
(N = 50, size 32: k ≤ 8 < 49, r ≤ 16 < 62).

So r ∈ {1, 2} sits exactly at the delivery threshold, and r ∈ {3, 5, 8, 16} tests
whether information beyond the conflict horizon still matters. k uses the same
range of mean degree, so range and k-NN can be compared at equal degree.

### Congestion vs density

These answer different questions, so there are two configs.

- **Congestion**: same 32 × 32 map, more robots. Crowding grows with N.
- **Density**: side grows with N, $N/\text{size}^2 \approx 0.03$
  (8/16², 16/23², 32/32², 64/45², 128/64²). Paths grow with the map, so the step
  limit grows too: $T_{\max} = 8 \cdot \text{size}$.

Maze is left out of scaling: its one-cell corridors already stall most robots at
N = 10, so it would only measure the corridors.

### Seeds

20 seeds per comparison. Paired differences use one value per instance, so 20
pairs give a usable interval for effects of a few percentage points. With
`--workers 4` the reported sweeps took 2 s (ladder), 3.5 min (topology) and
about 7–8 min per scaling config; the 128-robot global runs dominate. More seeds
can be added by editing the config. `smoke` has 2 seeds and is never used as evidence.

### Step limit

Under `on_target: finish`, an unsolved episode always runs to the step limit.
That limit could bias ISR if robots were still progressing when it hit. They
were not: in the reported sweeps, 1 of 1,601 unsolved runs had any arrival in
the last quarter of its limit. Unfinished robots are stuck, not slow.

## 3. Running

From the repository root, with the environment active:

```sh
python scripts/experiments/run_sweep.py experiments/ladder.yaml --workers 4
python scripts/experiments/analyze.py outputs/experiments/ladder
python scripts/experiments/plot_results.py outputs/experiments/ladder
```

To rerun from saved results, point `run_sweep.py` at the saved `config.yaml`
with a new `--out` folder. An existing results folder is never overwritten.

For one instance under several settings:

```sh
python scripts/experiments/plot_episode.py --map warehouse --n-agents 30 --seed 3 --topologies global range_1 knn_1 none
```

### Config keys

| Key | Meaning | Default |
|---|---|---|
| `name`, `kind` | output folder name; `ladder`, `topology` or `scaling` (which figures to draw) | required |
| `maps` | any of `random`, `warehouse`, `maze` | required |
| `n_agents`, `seeds` | lists of robot counts and distinct seeds | required |
| `topologies` | `global`, `none`, `range_<r>`, `knn_<k>`, `range_inf` | required |
| `size` | map side; a list pairs with `n_agents` by index | 32 |
| `max_steps` | step limit; a list pairs with `n_agents` | 256 |
| `window` | liveness window W | 10 |
| `obs_radius` | POGEMA sensing radius (kept separate from communication) | 3 |
| `oracle`, `oracle_timeout` | run LaCAM3 on each instance; seconds | false, 30 |
| `save_traces` | one JSON bundle per run | false |

Unknown keys, repeated seeds and unknown names are rejected before any run.

## 4. Outputs

Under `outputs/experiments/<name>/`:

| File | Content |
|---|---|
| `config.yaml` | exact copy of the config used |
| `metadata.json` | start/end time, workers, notes, run and error counts, Python/POGEMA (with Git commit)/NumPy/Matplotlib versions |
| `instances.json` | every instance: grid, starts, goals, id, step limit |
| `results.jsonl` | one line per run, written as each finishes (survives a crash) |
| `results.csv` | the same rows as a table |
| `traces/` | optional per-run trace bundle (`summary`, `raw`, conflict events) |
| `checks.txt`, `outcomes.csv`, `summary.csv`, `paired.csv` | written by `analyze.py` |
| `figures/` | written by `plot_results.py` |

### Run outcomes

Every run ends in exactly one outcome. None are dropped.

| `outcome` | Meaning |
|---|---|
| `solved` | every robot reached its goal (CSR = 1) |
| `time_limit` | the step limit ended the run with robots unfinished; ISR says how many arrived |
| `error` | an exception; `error` holds the message, `results.jsonl` the traceback |

An invalid config stops the sweep before any run. The oracle has its own status:
`disabled`, `unavailable` (no binary), `solved`, `timeout` (no answer within the
time limit) or `failed` (answered without a valid solution).

## 5. Metrics

All metrics come from the existing recorder and monitors; C7 only aggregates
them. For robot i, let $T_i$ be its first arrival step (None if it never
arrives) and $d_i(t)$ its Manhattan distance to its goal.

| Metric | Definition | Range and notes |
|---|---|---|
| ISR | $\frac{1}{N}\sum_i \mathbf 1[T_i \ne \text{None}]$ | [0, 1]; from POGEMA, checked against recorded arrivals |
| CSR | $\prod_i \mathbf 1[T_i \ne \text{None}]$ | 0 or 1 per run; its mean over instances is the share of fully solved instances |
| makespan, SoC | $\max_i T_i$, $\sum_i T_i$ | only for solved runs (first arrival, transitions convention) |
| $\rho_{\text{reach},i}$ | $-\min_t d_i(t)$ | ≤ 0; 0 = arrived, −3 = got within 3 cells; reported as the mean over robots |
| $\rho_{\text{live},i}$ | $\min_k \max_{j=k+1..k+W}\,[d_i(k) - d_i(j) - 1]$ | ≥ 0 means progress in every full W-window before arrival; None if no full window |
| $\rho_{\text{safe}}$ | $\min_t \min_{\text{active } i,j} d(p_i, p_j) - 1$ | ≥ 0 means no two active robots shared a cell; does not check swaps |
| mean degree | mean outgoing links per *active* robot, averaged over decision steps | potential receivers, not deliveries |
| messages per robot per step | delivered messages / (N × steps) | N includes finished robots |
| stalls | unfinished robots with $\rho_{\text{live}} < 0$, labelled epistemic / rule failure / unattributed | a diagnostic, not a causal proof |

Added by C7 in `coordination.py`, from the saved trace and the actions chosen:

- **conflict**: a decision where `blocking_neighbour` finds a robot j blocking
  i's claimed cell, using all claims. **heard**: j's claim was in i's inbox.
- **response**: wait, proceed (moved into the claim anyway), detour (another cell,
  shortest-path distance −1), retreat (distance +1). On a four-connected grid
  every move changes that distance by exactly 1, so there is no other case.
- **blocked moves**: the robot chose a move and the simulator refused it.
- **delay**: $T_i - D_i(s_i)$, with $D_i$ the static-map shortest distance.
  Arrived robots only.

E5 (mutual claim receipt) stays disabled in these sweeps, as its contract asks.
It measures receipt, not agreement or clearance.

## 6. Statistics

**Mean and interval.** For a metric M over K instances, $\bar M = \frac1K\sum_k M_k$.
The interval is a 95% percentile bootstrap: resample the K instance values
10,000 times with a fixed seed. Unknown values are left out and counted
(`n_missing`), never treated as zero.

**Paired differences.** For settings $C_1, C_2$ on the same instance,
$\Delta_k = M(C_1, k) - M(C_2, k)$. `paired.csv` reports the mean of $\Delta_k$,
its bootstrap interval, and how many instances had $\Delta_k > 0$, $= 0$, $< 0$.
This uses the matching; independent-sample intervals would hide it.

**Costs.** SoC and makespan exist only for solved runs. Averaging each setting
over its own solved runs would favour weak settings, which solve only easy
instances. So costs are compared only on instances solved by every compared
setting, and the count of such instances is always shown.

**Limits.** With 20 instances, the percentile bootstrap is approximate. When all
values are equal (for example ISR = 1 on every instance) the interval has zero
width; that means no variation was observed, not certainty. Overlapping bars are
not a test; read `paired.csv` for comparisons.

## 7. Figures

Error bars and bands are 95% bootstrap intervals over instances. Success is in %.
Each setting has one colour in every figure: none grey, global purple, LaCAM3
a charcoal dashed line, range in teal, k-NN in amber (darker = larger r or k).

Figures are numbered in reading order inside each experiment's `figures/` folder.

| Experiment | Figure | Question |
|---|---|---|
| ladder | `1_success_with_and_without_communication` | complete and individual success, global vs none (+ oracle), per map |
| ladder | `2_gain_from_communication_per_instance` | ISR(global) − ISR(none) on each instance; counts higher / equal / lower |
| ladder | `3_how_far_stuck_robots_stopped` | mean ρ_reach: how far short failed robots stopped |
| ladder | `4_cost_compared_with_oracle` | SoC(ours) / SoC(LaCAM3) per instance, each setting on the instances it solved (without the oracle: `4_cost_on_instances_all_settings_solved`) |
| ladder | `5_robots_at_goal_over_time` | share of robots at goal over time |
| oracle | `1_success_ours_vs_oracle` | ISR and CSR against N, with LaCAM3's solved share |
| oracle | `2_cost_compared_with_oracle` | mean SoC ratio to LaCAM3 against N, on solved instances (counts shown) |
| topology | `1_success_vs_communication_range` | ISR and ρ_reach against r, with global and none as bands |
| topology | `2_range_vs_knn_at_equal_degree` | range vs k-NN at the same measured mean degree |
| topology | `3_messages_vs_success` | delivered messages per robot per step vs ISR |
| topology | `4_was_the_blocker_heard` | share of conflicts whose blocker was heard |
| topology | `5_how_robots_respond_to_conflicts` | what robots did when the blocker was heard / not heard (pooled shares) |
| topology | `6_why_robots_got_stuck` | stalled robots per instance by cause |
| scaling | `1_success_as_fleet_grows` | ISR and CSR against N |
| scaling | `2_robustness_and_delay_as_fleet_grows` | ρ_reach and delay of arrived robots against N |
| scaling | `3_messages_as_fleet_grows` | message load against N |

### Checking runs by eye

Three scripts let you see what the numbers come from:

- `show_maps_and_communication.py` draws the three map types with real starts
  and goals (`the_three_map_types.png`), and the talk graph on one instance under
  each setting (`who_can_hear_whom.png`), using the project's topology code.
- `animate_episode.py` records an episode with **POGEMA's own renderer**
  (`outputs/animations/*.mp4`; needs `pip install imageio imageio-ffmpeg`). It does not use our plotting
  code, so it is an independent check of what the simulator did.
- `plot_episode.py` draws one instance under several settings: paths, conflict
  responses (filled = heard), and each robot's distance to goal over time.

### Why the maps cannot explain differences between settings

Nothing in the project learns. The planner is A* plus fixed priority rules, and
every robot is given the static wall map before it starts, because A* needs it.
That knowledge is identical under every communication setting, so it cannot cause
a difference between settings; only the delivered messages can. Random and maze
maps are regenerated for every seed, and the three map types check that a result
does not depend on one geometry.

## 8. Assumptions and limits

- **Perfect channel only.** Loss and delay (E1/E2 extensions) are not studied here.
- **One planner.** Results describe the team's simplified A* + yield planner, not
  DCMAPF in general and not any optimal method.
- **Collision semantics matter.** POGEMA's priority collision system lets one robot
  win a contested cell even without messages. Results depend on it.
- **Synthetic maps.** Three generated 32 × 32 map types, not benchmark maps.
- **Oracle.** LaCAM3 runs only when `LACAM3_BINARY_PATH` points to a working binary.
  Its costs use the project's first-arrival convention. LaCAM3 is a near-optimal
  reference, not a proven optimum under POGEMA's disappear-on-arrival semantics.
- **Runtime.** `runtime_s` is wall time per episode, measured while other worker
  processes run, so compare it only within one sweep.
- **Delay** covers arrived robots only. Read it with ISR, never alone.
