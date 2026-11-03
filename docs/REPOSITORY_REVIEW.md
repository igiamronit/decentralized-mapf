# Repository review — 2 November 2026

The implemented simulation modules work together on the tested fixtures, and the
confirmed defects below have been fixed. The research project remains incomplete:
C7 orchestration and C9 experiments/reporting are absent. Passing tests does not
establish planner completeness, paper reproduction, or a bug-free repository.

## Findings, in severity order

| Severity / status | Location | Evidence, impact and resolution |
|---|---|---|
| High / outstanding deliverable | [Guide C7/C9](TEAM_BUILD_GUIDE.md#c7--experiment-harness-charitha) | No experiment configs, sweep harness, matched-degree calibration, oracle/global/none error-bar plot, or statistical research results exist. These remain required work, rather than features supplied by this review. |
| Medium / fixed | [Planner `DCMAPFPlanner.act`](../decentralized_mapf/planner.py) | Start the lower-priority robot at (0,2) on `..... / ###.#`, receive a head-on claim, then observe it at (0,3) without a current peer claim. It used to move down toward the old refuge instead of left toward its goal. The goal path is now recomputed on release and checked against remaining current claims. Regression covers empty inbox, stale peer and another sender. |
| Medium / fixed | [Adapter `_parse_result`](../decentralized_mapf/oracle/lacam_adapter.py) | A solution with rows 0 and 10^12 previously materialized `set(range(max_t+1))` before rejecting the gap. This could exhaust memory on malformed solver output. Continuity now checks sorted received timestamps, allocating by output row count. The regression rejects this sparse horizon without attempting the dangerous allocation. |
| Medium / fixed | [Runner `run_episode`](../decentralized_mapf/runner.py) | A recorder with seed 8 could label an environment actually seeded 7; incorrectly ordered recorder goals could also produce misleading diagnostics. The runner now rejects exposed recorder metadata that disagrees with the environment, including zero-step runs. Legacy minimal recorders remain supported. |
| Medium / fixed | [Recorder and row validator](../decentralized_mapf/metrics.py), [monitors](../decentralized_mapf/monitors.py) | Editing a raw row to `n_messages=-100` produced a summary reporting -100 transmissions. Live/reloaded rows now reject negative/inconsistent counts, invalid coordinate pairs, invalid graph values, impossible ages and out-of-fleet inbox IDs. Goal coordinates are checked too. This validates row structure, not instance feasibility, sidecar authenticity, or obstacle occupancy. |
| Medium / fixed test gap | [Adapter tests](../tests/test_lacam_adapter.py) | The timeout test returned `None` when no binary existed, without reaching its patched subprocess. It now supplies a binary path and asserts invocation. Added nonzero exit, missing output, launch failure and temp-directory cleanup checks. A local executable protocol stub also exercises real OS invocation with spaces in the executable path; it is not LaCAM3. Parser tests now assert the specific adapter error. |
| Low / fixed | [Runner argument validation](../decentralized_mapf/runner.py) | `max_steps=True` silently ran one step because bool subclasses int. It is now rejected; integer zero remains valid. |
| Low / deferred at user request | [Topology demo](../scripts/demos/topology_snapshot.py) | The original figure includes finished robots as communicating nodes, duplicates the range calculation, and labels equality of two endpoint positions as being stuck. The review initially changed these behaviors; the original demo source has since been restored intact for future development. Treat its markers as a heuristic, not a formal deadlock diagnosis. |
| Low / deferred at user request | [Both demos](../scripts/demos/) | Importing runs an episode and writes artifacts; environments/figures are not explicitly closed. The main-guard/cleanup edits were reverted at the user's request. Both scripts are restored byte-for-byte from their pre-review versions; future development can continue from the original source. |

The planner intentionally remains an incomplete static-map A* plus local yield
baseline. The global/no-passing-corridor test still stalls. Longer runs below
also have unfinished robots. No unconditional deadlock-freedom claim is justified.

## Requirements and documentation reconciliation

- Read the sole applicable `AGENTS.md`, README, entire build guide/specification,
  environment results, E5 contract and the two-page proposal. Reviewed both
  preserved figures. The original proposal/figures remain historical artifacts;
  their deadlock labels and promised guarantees are not current test evidence.
- The specification used `FailureModel.corrupt`, `MetricsCollector`, and
  post-action recording. Those conflict with the frozen `Channel.deliver`,
  `Metrics`, addressed per-edge delivery, and pre-action K+1-row trace. The
  architecture and examples now describe the actual frozen interfaces. There
  are no legacy-name aliases or separate exported `PriorityYield` class.
- Setup now uses the pinned requirements consistently, documents fresh Python
  3.13 environments on Windows and macOS/Linux, and declares pytest in
  `requirements-dev.txt`. A preexisting Windows virtual environment is optional,
  not a repository prerequisite. Direct runtime dependencies remain pinned;
  transitive dependencies are not locked.
- Removed the README's stale statement that the oracle itself was pending.
  The adapter exists; executable verification and experiment integration remain
  separate obligations. Historical Windows solver/cost results are not claimed
  as verification of the current adapter on macOS.
- The guide's demand that oracle/global/none bars must always order correctly
  was stronger than the evidence allows. It now explicitly treats ordering as
  an expected trend to investigate, not sufficient proof of correctness. The
  required matched comparison and error bars remain pending; no requirement was
  removed to make a failing run pass. The near-optimal oracle objective and
  finish-mode first-arrival reporting still require the documented caveat.
- Kept the existing liveness, first-arrival, solved-only cost, one-hop knowledge,
  independent sensing/communication and default-off E5 contracts. The bounded
  delay lemma remains an unproved extension; positive-delay claims are ignored
  by the current planner. No loss/delay/failure feature was added.

## Review coverage and data flow

| First-party area | Coverage and integration boundary |
|---|---|
| Interfaces, package exports, channel | Read every module. Topology indices are local to active positions; runner restores stable IDs. Perfect channel is pass-through; other channel behaviors in tests are doubles. |
| Communication / graph statistics | Reviewed all four models, parameter checks, Manhattan ties, directed links, weak components and isolated robots. Existing tests independently check every simple directed graph on four nodes. |
| Pathfinding / planners | Reviewed all functions, observation-to-path advancement, compose snapshots, priority, refuge persistence/release and reset. Added BFS reference checks for all 64 binary 2×3 maps, plus the release regression. |
| Runner | Reviewed reset/observe/compose/deliver/record/act order, per-recipient deep copies, finished IDs, channel queues, cutoff, environment termination, caller-owned cleanup and optional hooks. Exercised with real POGEMA and test collaborators. |
| Metrics / monitors | Reviewed raw/native metric separation, first arrivals, finite windows, safety exclusions, attribution limits, delivered-message denominator, JSON migration and terminal intentions. Added corruption tests and formula checks over all 1,024 five-sample distance signals with windows 1–5. |
| Optional E5 | Read full module, contract and tests: pair detection, mutual fresh payload receipt, recurrence, censoring, sparse IDs and persistence. Existing real-episode tests verify that enabling it leaves core trajectories/results unchanged. It remains optional; saved E5 episodes are restored, not independently recomputed by `from_data`. |
| Centralized oracle | Read all adapter, conversion, parser, validator, cost and ratio code/tests. Reviewed argument-list subprocess invocation (no shell), temp cleanup, timeout/failure semantics, coordinate conversion, padded paths and full-trajectory validation. Actual solver unavailable. |
| Scripts | Read and ran all three. Verifier tests the simulator API, not planner success. Animation uses POGEMA's independent A* and prints raw native costs, not corrected project costs. Topology snapshot is an illustration on one trajectory. |
| Tests / configuration / tooling | Read all original 11 test modules; added `test_review_invariants.py`. Reviewed requirements, ignore rules and Git attributes. No first-party build/package metadata, experiment configs, CI workflows, lint policy or type-check configuration exists. |
| Security / dependencies | Inspected first-party file access and external-process boundaries; scanned for common credential/private-key patterns without finding matches. No production access, deployment, push or commit. `pip check` passes. This is not a dependency-advisory audit or a claim that no secrets/vulnerabilities exist. |

Data flows from a seeded environment's own-state observations into planner
broadcasts, through the active topology and addressed channel transmissions into
inboxes/actions. The recorder snapshots pre-action state/delivery evidence;
offline monitors consume saved trace/intention data. The oracle independently
takes a static problem, shells out using an argument list, validates full paths
and calculates comparison costs. A future harness owns environment construction,
matched instances, persistence, aggregation and plots; it must not feed offline
robustness or oracle state back into the decentralized planner.

## Executed verification

Used an isolated `/private/tmp/mapf-review-env` with Python **3.13.12**,
NumPy **2.5.3**, Matplotlib **3.11.2**, pytest **9.2.0** and POGEMA Git commit
`2e27a16af86fe47dfa62ab2f685a659ed5dc9910` (verified installed provenance).
The shell's Python 3.11 and preexisting `.venv` lacked project/test dependencies
and were left untouched. Installing dependencies initially hit sandbox DNS
restrictions, then succeeded with approved network access.

| Check / command | Result |
|---|---|
| Baseline `python -m pytest -q -p no:cacheprovider` under coverage | 178 tests and 82 subtests passed before fixes. New release/boolean regressions were then observed failing. |
| Final `python -m pytest -q -p no:cacheprovider` | **213 tests and 108 subtests passed.** |
| `coverage run --branch --source=decentralized_mapf -m pytest ...`; affected metrics rerun with `--append` | **91% combined statement/branch coverage**, 883 statements, 55 missed; no claim of exhaustive path coverage. Scripts/dependencies are outside this measurement. |
| Seeded production pipeline invariants | 24 configurations: seeds 1/7 × fleets 10/25/100 × all four topologies; each repeated, for 48 real episodes of up to 24 steps. Checked reproducibility, legal movement/obstacles, active-pair safety, delivery counts and JSON summary reload. |
| Additional production smoke runs | Seed 7, 100 robots, 32×32 map, density 0.2, 256 steps, all four topologies. All completed the horizon and passed safety/reload checks; none solved the whole instance. These are local correctness fixtures, not C9 statistical results. |
| `python scripts/checks/verify_environment.py` at seeds 1 and 42 | All six checks passed for both, including 100-agent random-action episodes. |
| README concrete interface/topology/planner snippets and complete recorder example | Executed successfully; recorder example solved in 4 steps, SoC 8. Saved raw JSON reload reproduced the summary. Placeholder snippets require caller-provided collaborators, as documented. |
| Specification environment example | Executed successfully through termination with cleanup. |
| Both documented demos | Successfully wrote SVG, HTML and PNG under `outputs/`; inspected the generated topology image. The original scripts had also run successfully at baseline. After the user requested preserving the demo code, both were restored and verified byte-for-byte against their pre-review versions. They have since been rerun successfully in the repository-local `.venv-test` environment, documented below. Import-safety/cleanup improvements remain deferred. |
| `python -m compileall -q decentralized_mapf scripts tests`; `git diff --check` | Passed. |
| `python -m pip check` | No broken requirements. |
| Focused `ruff check --isolated --select E9,F decentralized_mapf scripts tests` | Passed. |
| Broad ad hoc `ruff check --isolated decentralized_mapf scripts tests` | Does **not** pass: import ordering, annotation/style conventions, exception preferences and similar diagnostics remain. No repository lint gate was disabled or introduced; unrelated style rewrites were avoided. |

Generated evidence is ignored by Git under `outputs/review/` (environment JSON,
coverage data and full production traces), with the README trace under
`outputs/traces/` and demos under `outputs/renders/` / `outputs/figures/`.
The 100-agent fixtures delivered 479,108 / 0 / 83,474 / 23,264 transmissions
for global / none / range-3 / k-NN-2, respectively. These counts describe the
saved smoke fixtures only. Original untracked Finder `Icon` files were preserved.

## Repository-local test environment rerun

At the user's request, created a persistent Python **3.13.12** environment in
`.venv-test/` and installed `requirements-dev.txt`, including its pinned runtime
dependencies. The existing Python 3.11 `.venv/` was preserved. `.venv-test/` is
ignored by Git; README documents activation and reuse.

Executed with `.venv-test/bin/python`:

- `-m pytest -q -p no:cacheprovider --junitxml=outputs/review/local-test-env/pytest.xml`:
  **213 tests and 108 subtests passed**, in 17.12 seconds.
- All six environment checks passed at seeds **1** and **42**.
- Both original, restored demo scripts ran successfully and exported their
  artifacts. Their source files still match the pre-review Git versions exactly.
- `-m pip check` and `-m compileall -q decentralized_mapf scripts tests` passed.

Saved the test XML, check exit statuses, command logs, dependency versions,
installed POGEMA provenance and resolved package list under
`outputs/review/local-test-env/`. The actual LaCAM3 executable remains unavailable;
oracle tests still use the explicitly documented stubs.

## Subsequent environment recheck

Verified `.venv-test/bin/python` resolves inside the repository's isolated
environment and uses Python **3.13.12**, NumPy **2.5.3**, Matplotlib **3.11.2**
and pytest **9.2.0** from that environment. Installed POGEMA provenance still
matches commit `2e27a16af86fe47dfa62ab2f685a659ed5dc9910`.

Reran the entire suite in two fresh processes, treating warnings as errors:

```sh
PYTHONHASHSEED=1 .venv-test/bin/python -m pytest -q -W error -p no:cacheprovider --junitxml=outputs/review/recheck/hashseed1.xml
PYTHONHASHSEED=101 .venv-test/bin/python -m pytest -q -W error -p no:cacheprovider --junitxml=outputs/review/recheck/hashseed101.xml
```

Both passed **213 tests and 108 subtests**, in 12.90 and 12.37 seconds,
respectively. No test failures or warnings promoted to errors were reported.
All six environment checks passed again at seeds 1 and 42, both original demos
ran successfully, and dependency consistency, Python compilation and
`git diff --check` passed. Demo sources were verified against their original
Git versions; they were not edited.

Saved the XML reports, environment evidence, process logs, interpreter/package
provenance and Python source fingerprints under `outputs/review/recheck/`.
No additional implementation changes were needed. This recheck does not prove
the absence of bugs or remove the limitations below; the actual LaCAM3 binary
is still unavailable on this host.

## Verification limits and next integration work

No installed LaCAM3 binary was found. Its current CLI/runtime/DLL compatibility,
real solve quality, timeout behavior and current cost convention against solver
output remain unverified here. Stub tests must not be reported as solver results.
The public `timeout` currently gives the subprocess up to five extra seconds of
wall-clock grace, as implemented; it is not a strict end-to-end deadline.

Windows activation/DLL setup was reviewed but not executed on this macOS host.
The executable protocol-stub test uses a POSIX shebang and is explicitly skipped
on Windows; the mock adapter tests remain platform independent.
There is no configured build, type checker or CI suite to run. A dependency
vulnerability-database audit, external bibliography verification, all simulator
collision modes and exhaustive multi-agent planner behavior are outside the
verified results. The proposal PDF was text-extracted for requirements, not
edited or republished. Sandbox font-cache warnings occurred; exports succeeded.

Next owners should build C7 against these shared contracts, retain map/start/goal
evidence with each run, provision and verify the actual oracle, complete the
matched core comparisons/calibration, and characterize planner failures on
solvable instances before making research claims or extending channel behavior.
