# E5 measurement contract: time to mutual claim receipt

This defines Dhanvi's E5 instrumentation of Harsh's existing planner. The
definition is fixed here; the tracker and optional recorder hooks are implemented.
Read `TEAM_BUILD_GUIDE.md` and `PROJECT_SPEC.md` first. E5 is an extension after
core validation. The specification calls this experiment E10; its experiment
numbers differ from the guide's extension numbers.

## What “agreement” means here

For E5, **agreement is the first decision round of a conflicting pair's episode
in which both agents receive the other's current-round claim**. Call the metric
**time to mutual claim receipt** in figures and reports. The guide's proposed name
`mean_rounds_to_agreement` may be retained with this definition/version attached.

This operationalizes the guide's time-to-mutual-knowledge framing. It measures
first-order receipt in both directions, not an acknowledgement protocol, common
knowledge, agreement on revised actions, or physical conflict resolution. An
external recorder can establish both deliveries even though neither agent gets
an acknowledgement proving the other's receipt. Perfect communication can give
agreement by this definition while the planner still stalls.

## Round and timing convention

One round is one nonterminal runner timestep `t`:

`observe all active agents -> compose all broadcasts -> deliver -> record -> act -> env.step`

There is no inner negotiation loop. Count elapsed rounds as
`t_agreement - t_start`, so receipt at the starting timestep is **0**, and receipt
at the next timestep is **1**. Do not add one. Rounds advance even when nothing
is delivered; count timesteps, not messages or calls to `act()`.
The terminal trace row contains no broadcasts/actions and is not a round.

## Conflict episodes

Use pre-decision claims for all active agents, independently of topology and
delivery. For agent `i`, let `p_i` be its current position and `q_i` be its first
broadcast `next_cells` entry, or `p_i` when that list is empty. A pair conflicts
when either:

- `q_i == q_j` and at least one agent intends to move (same destination,
  including a moving agent targeting a stationary occupant); or
- `q_i == p_j` and `q_j == p_i`, with both agents intending to move (head-on swap).

This is pairwise immediate-claim conflict, not a prediction over all three
broadcast cells. Detect it symmetrically; `blocking_neighbour()` is a directional
priority/blocker helper and is not by itself this predicate.

An episode starts at the first conflicting decision round for an unordered
pair `(min(i,j), max(i,j))`. Preserve its start across consecutive conflicting
rounds, even if the claimed cells or conflict type change. End it on the first
decision round where the pair no longer conflicts or either agent is inactive.
A later recurrence starts a new episode with a new sequence number. Multi-agent
contention produces one episode per conflicting pair; label aggregates pairwise.

Detect starts from recorded claims, not only from an agent receiving a blocker
message. Otherwise missing communication would hide conflicts from the metric.
The recorder's global evidence is for measurement only and must never feed
back into agent decisions.

## Receipt and episode outcomes

For a still-conflicting pair at round `t`, require an actual message from `j`
in `i`'s inbox **and** one from `i` in `j`'s inbox, both with `sent_at == t` and
payloads matching the corresponding current broadcasts. Check this after
delivery and before actions. Current-round receipt in opposite directions at
different timesteps does not accumulate: the planner does not retain stale
claims. Directed k-NN adjacency or component membership alone proves nothing
about bidirectional delivery.

Record the first qualifying `t_agreement` once per episode. Keep tracking that
episode until its conflict predicate ends, so a persistent conflict does not
generate another sample every round. Missing messages, loss of range, clearing
`_yield_to`, or one agent choosing WAIT are not receipt events.

- If a conflict ends before mutual receipt, retain it as
  `ended_without_agreement`; give it no numeric agreement duration.
- If it is still open without receipt when the run ends, retain it as
  `censored_at_end`, with the final trace timestamp as the observation limit.
- An episode with an agreement timestamp stays counted as agreed, even if the
  physical conflict remains open at the run limit.

Compute mean/max elapsed rounds only over agreed episodes; return `None` when
there are none. Always also report `n_conflicts`, `n_agreed`,
`n_ended_without_agreement`, `n_censored`, and agreement coverage
`n_agreed / n_conflicts` (`None` when no conflicts). These categories partition
all episodes. A low successful-sample mean with low coverage is not evidence
of good communication. Retain per-episode timestamps, pair IDs, sequence number,
outcome and duration for reproducibility. Use definition version
`mutual_current_claim_receipt_v1` in saved output.

## Integration boundaries

Implement a separate tracker/recorder collaborator. Reuse the runner and existing
metrics; preserve frozen `Message`, `StepRecord`, `Planner`, and `record()`
signatures. E5 is disabled by default: supply a fresh `ConsensusTracker()` as
`Metrics(..., consensus_tracker=...)` to enable collection. Use a fresh recorder
and tracker per episode. Core experiments keep the default until the required
validation is complete. Existing metrics capture happens before `act()`, which is sufficient
for this receipt metric. Snapshot the all-agent pre-decision claims and actual
timestamped deliveries into an E5 sidecar for offline evaluation and JSON reload.
`Metrics.intents` plus `StepRecord.inbox_senders` alone cannot prove freshness:
the latter omits individual message timestamps/payloads. Do not reconstruct
deliveries from potential graph edges or infer missing evidence as success.

The runner calls `capture_e5_round(t, positions, active, broadcasts, inboxes)`
after delivery and `finalize_e5(terminal_t)` once at the final state. The hooks
do nothing when disabled. Position snapshots may be ID-indexed lists or mappings
with sparse original IDs; mappings need not include finished robots. Results
are under `summary()['e5']`; `to_data()['e5']` also contains per-round evidence.
Both are `None` when disabled. `Metrics.from_data()` accepts old bundles without
E5 and restores enabled bundles for offline summaries.

Do not invoke `compose()` or `act()` an extra time for logging, change their
order, inspect another agent's cache inside decisions, add ACK messages, or
change A*, priorities, yielding, refuge release, sensing, or channel policies.
Save generated traces under `outputs/`. Keep observation and communication
independent. Positive-delay messages are currently ignored by the planner, so
they cannot satisfy this definition; changing that requires a separately
documented delayed-message policy, not an instrumentation fix.

If physical clearance is also studied, report it separately. Its definition and
required action/position evidence need their own contract; disappearance of this
immediate-claim predicate alone does not prove a bottleneck has been passed.

## Verification criteria

- Same-round bidirectional fresh delivery gives 0; first delivery at the next
  still-conflicting round gives 1.
- One-way delivery, stale messages, and empty inboxes do not give agreement.
- Repeated detection preserves the start; repeated receipt yields one sample.
- A disappearing conflict without receipt is `ended_without_agreement`;
  a still-open one at cutoff is `censored_at_end`.
- Same-pair recurrence creates a new episode; changing cells while continuously
  conflicting does not. Three agents claiming one cell create three pairs.
- Perfect-global/no-passing-corridor can have receipt agreement and still stall.
- No-conflict and no-agreement summaries handle empty aggregates with `None`.
- Terminal rows do not create episodes or receipt events. JSON reload reproduces
  summaries, and enabling the tracker leaves actions and trajectories unchanged.

Tracker tests live in `tests/test_e5_consensus.py`. Episode tests in
`tests/test_episode_integration.py` cover default-off behavior, opt-in recording,
cutoff/terminal handling, JSON reload, and unchanged core trajectories/results.
The extension experiments and their plots remain pending.
