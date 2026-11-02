"""Trace recording, optional passive E5 tracking, and offline spec summaries."""

from copy import deepcopy
from dataclasses import asdict
from statistics import mean

from .interfaces import StepRecord
from . import monitors
from .e5_consensus import ConsensusTracker

COST_DEFINITION = "first_arrival_steps_v1"


class Metrics:
    """One fresh recorder per run, using the frozen runner's record signature.

    Pass planner.intended_steps as intent_provider for offline blocker diagnosis.
    The optional runner capture_environment hook copies POGEMA's ISR/CSR and raw
    wrapper metrics. Solved-run SoC and makespan use recorded first arrivals:
    the pinned cost wrapper forgets early arrivals when robots finish apart.
    An early caller cutoff has no terminal ISR/CSR, so costs remain None too.

    summary() evaluates monitors only after the run. to_data() provides a JSON
    serializable raw bundle, including intentions required for reproducible
    diagnosis; writing files and aggregation belong to the experiment harness.
    E5 is disabled unless a fresh consensus_tracker is supplied explicitly.
    """

    def __init__(self, goals, *, seed, window=10, intent_provider=None,
                 consensus_tracker=None):
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError("seed must be an integer")
        if isinstance(window, bool) or not isinstance(window, int) or window < 1:
            raise ValueError("window must be a positive integer")
        self.goals = [tuple(goal) for goal in goals]
        if not self.goals:
            raise ValueError("At least one goal is required")
        if any(len(goal) != 2 or any(isinstance(v, bool) or not isinstance(v, int)
                                    or v < 0 for v in goal) for goal in self.goals):
            raise ValueError("Goals must be nonnegative integer coordinate pairs")
        self.seed, self.window, self.intent_provider = seed, window, intent_provider
        self.trace, self._intents, self.environment_metrics = [], {}, {}
        self.e5 = consensus_tracker

    @property
    def intents(self):
        """Intentions for decision rows; the last trace row is terminal.

        The provider still holds the previous decision's cache at termination.
        Exclude that row rather than persisting a claim that was never composed.
        The recorder is consumed offline, after the final state has been added.
        """
        return {t: claims for t, claims in self._intents.items()
                if t < len(self.trace) - 1}

    def capture_environment(self, infos):
        """Copy terminal wrapper metrics, without evaluating any specification."""
        if infos and "metrics" in infos[0]:
            self.environment_metrics = deepcopy(infos[0]["metrics"])

    def record(self, t, positions, graph_stats, arrived, inboxes):
        """Snapshot state/deliveries before actions, including one terminal row."""
        if t != len(self.trace) or len(positions) != len(self.goals):
            raise ValueError("Records must be contiguous from zero with stable IDs")
        ages = [t - msg.sent_at for msg in arrived]
        if any(age < 0 for age in ages):
            raise ValueError("A delivered message cannot come from the future")
        row = StepRecord(
            t=t, positions=[tuple(p) for p in positions],
            mean_degree=graph_stats["mean_degree"], n_components=graph_stats["n_components"],
            n_messages=len(arrived),
            inbox_senders={i: [msg.sender for msg in inboxes.get(i, [])]
                           for i in range(len(self.goals))},
            max_age=max(ages, default=0),
        )
        monitors.validate_record(row, t, len(self.goals))
        self.trace.append(row)
        if self.intent_provider is not None:
            self._intents[t] = {i: tuple(cell) for i, cell in self.intent_provider().items()
                                if tuple(positions[i]) != self.goals[i]}

    def capture_e5_round(self, t, positions, active, broadcasts, inboxes):
        """Capture E5 claims and actual deliveries before planner actions."""
        if self.e5 is not None:
            self.e5.record_round(t, positions, active, broadcasts, inboxes)

    def finalize_e5(self, terminal_t):
        """Finalize E5 episodes at the terminal trace timestamp."""
        if self.e5 is not None:
            self.e5.finalize(terminal_t)

    def summary(self):
        """Offline results, preserving unknowns and costs only for solved runs.

        pct_epistemic is a fraction in [0,1] among attributed stalls, None when
        none are attributed. n_unattributed is always reported alongside it.
        Message denominator is initial fleet size times actual environment steps;
        graph means exclude the terminal row. These conventions are fixed before
        sweeps, rather than chosen after inspecting a performance curve.
        """
        if not self.trace:
            raise ValueError("Cannot summarize an empty trace")
        n, steps = len(self.goals), self.trace[-1].t
        reach = [monitors.rho_reach(self.trace, i, self.goals) for i in range(n)]
        live = [monitors.rho_live(self.trace, i, self.goals, self.window) for i in range(n)]
        observed_live = [value for value in live if value is not None]
        causes = monitors.deadlock_causes(self.trace, self.goals, self.window, intents=self.intents)
        counts = {label: list(causes.values()).count(label)
                  for label in ("epistemic", "rule_failure", "unattributed")}
        attributed = counts["epistemic"] + counts["rule_failure"]
        decision_rows = self.trace[:-1]
        messages = sum(row.n_messages for row in decision_rows)
        solved = self.environment_metrics.get("CSR") == 1.0
        arrivals = [monitors.first_arrival(self.trace, i, self.goals) for i in range(n)]
        if solved and any(t is None for t in arrivals):
            raise ValueError("CSR reports success but the trace is missing an arrival")
        return {
            "seed": self.seed, "n_agents": n, "steps": steps, "window": self.window,
            "liveness_definition": "bounded_eventual_progress_v1",
            "cost_definition": COST_DEFINITION,
            "ISR": self.environment_metrics.get("ISR"),
            "CSR": self.environment_metrics.get("CSR"),
            "makespan": max(arrivals) if solved else None,
            "SoC": sum(arrivals) if solved else None,
            "n_arrived": sum(value == 0 for value in reach),
            "n_deadlocked": len(causes), "n_epistemic": counts["epistemic"],
            "n_rule_failure": counts["rule_failure"], "n_unattributed": counts["unattributed"],
            "pct_epistemic": counts["epistemic"] / attributed if attributed else None,
            # String keys keep summaries identical after a JSON round trip.
            "deadlock_causes": {str(i): label for i, label in causes.items()},
            "rho_reach_mean": mean(reach),
            "rho_live_mean": mean(observed_live) if observed_live else None,
            "n_liveness_evaluated": len(observed_live),
            "rho_safe": monitors.rho_safe(self.trace, self.goals),
            "n_messages": messages,
            "messages_per_agent_per_step": messages / (n * steps) if steps else 0.0,
            "mean_degree": mean(row.mean_degree for row in decision_rows) if steps else None,
            "mean_components": mean(row.n_components for row in decision_rows) if steps else None,
            "environment_metrics": deepcopy(self.environment_metrics),
            "e5": self.e5.summary() if self.e5 is not None and self.e5._finalized else None,
        }

    def to_data(self):
        """Raw experiment persistence bundle; includes frozen rows plus diagnostic sidecar."""
        return {"seed": self.seed, "window": self.window, "goals": list(self.goals),
                "liveness_definition": "bounded_eventual_progress_v1",
                "cost_definition": COST_DEFINITION,
                "trace": [asdict(row) for row in self.trace],
                "intents": deepcopy(self.intents),
                "environment_metrics": deepcopy(self.environment_metrics),
                "e5": self.e5.to_data() if self.e5 is not None and self.e5._finalized else None}

    @classmethod
    def from_data(cls, data):
        """Restore a JSON round-trip for offline re-evaluation, without a planner."""
        if data.get("liveness_definition") != "bounded_eventual_progress_v1":
            raise ValueError("Unsupported liveness definition")
        if data.get("cost_definition") not in (None, COST_DEFINITION):
            raise ValueError("Unsupported cost definition")
        recorder = cls(data["goals"], seed=data["seed"], window=data["window"])
        for values in data["trace"]:
            values = dict(values)
            values["positions"] = [tuple(p) for p in values["positions"]]
            values["inbox_senders"] = {int(i): list(ids) for i, ids in values["inbox_senders"].items()}
            row = StepRecord(**values)
            monitors.validate_record(row, len(recorder.trace), len(recorder.goals))
            recorder.trace.append(row)
        recorder._intents = {int(t): {int(i): tuple(cell) for i, cell in claims.items()}
                            for t, claims in data["intents"].items()}
        recorder.environment_metrics = deepcopy(data["environment_metrics"])
        if data.get("e5") is not None:
            recorder.e5 = ConsensusTracker.from_data(data["e5"])
        # Validate restored timing and stable IDs even when no summary is requested.
        monitors.rho_reach(recorder.trace, 0, recorder.goals)
        return recorder
