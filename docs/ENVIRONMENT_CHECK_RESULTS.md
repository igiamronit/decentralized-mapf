# C1 - Environment Verification

Verified locally on **12 October 2026**. All six environment checks passed.
This completes C1; it does not validate the future planner or communication layer.

## Reproduce

From the repository root in PowerShell:

```powershell
.\mapf-env\Scripts\python.exe scripts/checks/verify_environment.py
```

One verifier replaces the previous `smoke_test.py` and `collision_behavior.py`.
Each check is a separate function; importing the module does not run the suite.
The command prints PASS/FAIL, saves evidence to
`outputs/verification/environment.json`, and exits 1 if any check fails.
Options: `--seed <integer>` and `--output <path>`. Default seed: **1**.

## Environment

- Python **3.13.0**, POGEMA **2.0.0a**, NumPy **2.5.3**.
- Installed POGEMA Git revision: `2e27a16af86fe47dfa62ab2f685a659ed5dc9910`.
- Explicit settings: `observation_type='POMAPF'`, `collision_system='priority'`,
  `on_target='finish'`, `integration=None`.
- The local Python launcher prints a path-resolution warning before execution;
  the verifier still runs successfully and returns exit code 0.

## Checklist and measured evidence

| Check | Result | Evidence |
|---|---|---|
| 100-agent execution | PASS | 64 x 64 grid, density 0.3, observation radius 3, seed 1. Completed 256 steps by reaching the configured time limit. |
| Conflicting movements | PASS | Same-cell contention allowed one robot to move; adjacent swaps were blocked; opposing corridor robots remained adjacent and stalled. No co-occupancy in these cases. |
| External positions and goals | PASS | Public getters returned all agent IDs; coordinates matched internal state after removing border padding. Positions and fixed goals were read throughout the 100-agent run. |
| Custom per-agent actions | PASS | Submitted move-right for robot 0 and wait for robot 1. Positions changed from `[[0,0],[0,8]]` to `[[0,1],[0,8]]`. |
| Seed reproducibility | PASS | Same seed reproduced map, starts, goals, observations, rewards, flags, and state over eight action steps, both after reset and in a separate environment. Seed 2 produced a different instance. |
| Observations and metrics | PASS | Confirmed POMAPF fields, active flags, terminal metric location, and success/cost values on a known two-step episode. |

### Timing and scope

The recorded seed-1 run took **0.332 seconds total**: 0.010 seconds for environment
creation/reset and 0.321 seconds for the rollout, including state checks.
Imports and interpreter startup are excluded. This is one local measurement,
not an averaged performance benchmark; later timings will vary.

Actions came from a dedicated seeded NumPy random generator. Reaching the time
limit means the simulator completed its execution, not that every robot arrived.
Terminal metrics: `ISR=0.04`, `CSR=0.0`, `ep_length=248.26`.

### Collision evidence

Coordinates below exclude POGEMA's border padding. Opposing robots started at
`[[0,0],[0,8]]` and were repeatedly driven toward each other for 12 steps.
They reached `[[0,4],[0,5]]` after four steps and stayed there through step 12.
This supports using stalls/non-arrival as failure measures. It is a finite check
under the stated collision mode, not a proof for every possible configuration.

### State and coordinate conventions

- Map-relative positions: `env.unwrapped.get_agents_xy(ignore_borders=True)`.
- Map-relative goals: `env.unwrapped.get_targets_xy(ignore_borders=True)`.
- Map without padding: `env.unwrapped.get_obstacles(ignore_borders=True)`.
- Coordinates are **row, column**. Internal `grid.positions_xy` and
  `grid.finishes_xy` include an offset equal to `obs_radius`.
- POMAPF `xy` and `target_xy` are relative to **each agent's initial position**.
  At reset every agent's `xy` is `(0,0)`. Do not mix these with map coordinates.
- Reached agents become inactive under `on_target='finish'`. The default state
  getters retain their IDs/last coordinates; use `info[i]['is_active']` when
  deciding which robots still participate in communication or occupancy checks.

### Observations and available metrics

With observation radius 3, each POMAPF observation contains:

| Field | Shape | Meaning |
|---|---|---|
| `obstacles` | 7 x 7 | Local obstacle observation |
| `agents` | 7 x 7 | Local agent observation |
| `xy` | 2 | Position relative to this agent's start |
| `target_xy` | 2 | Goal relative to this agent's start |

`reset()` returns `(observations, infos)`. `step(actions)` returns
`(observations, rewards, terminated, truncated, infos)`.
Reset and intermediate-step info contain per-agent `is_active` flags. Aggregate
metrics appear at episode end in **`infos[0]['metrics']`**.

- Default finish-mode metrics: `ISR`, `CSR`, and `ep_length`.
- Add `SumOfCostsAndMakespanMetric` to obtain `SoC` and `makespan`.
- Known episode: robots first arrive at steps 1 and 2. Verified default values
  `ISR=1.0`, `CSR=1.0`, `ep_length=1.5`; with the cost wrapper,
  `SoC=3`, `makespan=2`.
- `ep_length` is mean per-agent episode length in this mode, not makespan.
- Communication counts, deadlock classification, and STL robustness remain our
  later project work; they are not supplied by these metrics.

Raw JSON includes the full scale configuration, package provenance, collision
frames, instance hashes, observation shapes, and reset/intermediate/terminal info.
