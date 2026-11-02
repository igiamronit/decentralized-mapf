"""Offline properties over frozen StepRecords; never steer the planner.

Reachability uses the guide's nonpositive shortfall convention. Liveness follows
its eventually-closer formula, correcting the inconsistent endpoint pseudocode.
On an integer grid, d(j)<d(k) is d(k)-d(j)-1 >= 0. Thus zero satisfies every
monitor, consistently. Only full windows starting before first arrival are
evaluated; an unobserved window returns None. A violation is an observed stall,
not a proof of permanent deadlock: necessary detours can violate this property.
"""

from itertools import combinations
from math import isfinite

from .communication import manhattan
from .interfaces import Message
from .planner import blocking_neighbour


def validate_record(row, t, n_agents):
    """Reject malformed recorded evidence before it can produce research scores.

    Used on live snapshots and saved bundles. Map bounds are unavailable here;
    callers still own instance validation. Coordinates must be integer pairs,
    graph values describe at most the original fleet, and delivery counts must
    agree with the inbox evidence. Unknown liveness windows remain valid.
    """
    def integer(value, lower, upper=None):
        return (not isinstance(value, bool) and isinstance(value, int)
                and value >= lower and (upper is None or value <= upper))

    if not integer(row.t, 0) or row.t != t or len(row.positions) != n_agents:
        raise ValueError("Trace must be contiguous from t=0 with stable agent IDs")
    if any(not isinstance(p, (tuple, list)) or len(p) != 2
           or any(not integer(v, 0) for v in p) for p in row.positions):
        raise ValueError("Trace positions must be nonnegative integer coordinate pairs")
    if (isinstance(row.mean_degree, bool) or not isinstance(row.mean_degree, (int, float))
            or not isfinite(row.mean_degree) or not 0 <= row.mean_degree <= max(0, n_agents - 1)
            or not integer(row.n_components, 0, n_agents)):
        raise ValueError("Invalid trace graph statistics")
    if not integer(row.n_messages, 0) or not integer(row.max_age, 0, t):
        raise ValueError("Invalid trace message count or age")
    if (not isinstance(row.inbox_senders, dict)
            or any(not integer(i, 0, n_agents - 1) or not isinstance(ids, list)
                   or any(not integer(sender, 0, n_agents - 1) for sender in ids)
                   for i, ids in row.inbox_senders.items())
            or sum(map(len, row.inbox_senders.values())) != row.n_messages):
        raise ValueError("Trace inbox evidence disagrees with delivered messages")


def _validate(trace, goals):
    if not trace:
        raise ValueError("A trace must contain at least the initial state")
    if any(row.t != t or len(row.positions) != len(goals) for t, row in enumerate(trace)):
        raise ValueError("Trace must be contiguous from t=0 with stable agent IDs")


def first_arrival(trace, i, goals):
    """First recorded goal hit, or None; goals/positions use map coordinates."""
    return next((row.t for row in trace if tuple(row.positions[i]) == tuple(goals[i])), None)


def rho_reach(trace, i, goals):
    """0 means reached; -3 means the closest recorded approach was three cells."""
    _validate(trace, goals)
    return -min(manhattan(row.positions[i], goals[i]) for row in trace)


def _progress_windows(trace, i, goals, W):
    _validate(trace, goals)
    if isinstance(W, bool) or not isinstance(W, int) or W < 1:
        raise ValueError("W must be a positive integer number of steps")
    arrival = first_arrival(trace, i, goals)
    return [(k, max(manhattan(trace[k].positions[i], goals[i]) -
                    manhattan(trace[j].positions[i], goals[i]) - 1
                    for j in range(k + 1, k + W + 1)))
            for k in range(len(trace) - W) if arrival is None or k < arrival]


def rho_live(trace, i, goals, W=10):
    """Min over full windows of max future strict-progress margin.

    rho = min_k max_{j=k+1..k+W} [d(k)-d(j)-1]. A value >=0
    satisfies the bounded eventual-progress property; <0 violates it.

    There is no padding after the end of an episode, and no requirement for
    finished robots to keep moving. Retain None in raw results; do not turn an
    unobserved short run into a liveness success or a deadlock.
    """
    return min((margin for _, margin in _progress_windows(trace, i, goals, W)), default=None)


def stall_start(trace, i, goals, W=10):
    """First start of a complete non-progress window, or None."""
    return next((k for k, margin in _progress_windows(trace, i, goals, W) if margin < 0), None)


def rho_safe(trace, goals):
    """Minimum active-pair separation minus one; None if no active pair exists.

    Under finish semantics, a robot is excluded on and after its first goal hit,
    even though its final coordinates remain in the trace. This checks cell
    occupancy, not edge swaps. It is an implementation sanity check, not evidence
    of a collision-avoidance guarantee supplied by our coordination algorithm.
    """
    _validate(trace, goals)
    arrivals = [first_arrival(trace, i, goals) for i in range(len(goals))]
    margins = []
    for row in trace:
        active = [i for i, arrival in enumerate(arrivals) if arrival is None or row.t < arrival]
        margins.extend(manhattan(row.positions[i], row.positions[j]) - 1
                       for i, j in combinations(active, 2))
    return min(margins, default=None)


def deadlocked_agents(trace, goals, W=10):
    """Unfinished agents with an observed liveness violation (historical stalls)."""
    _validate(trace, goals)
    return {i for i in range(len(goals)) if rho_reach(trace, i, goals) < 0
            and (margin := rho_live(trace, i, goals, W)) is not None and margin < 0}


def deadlock_causes(trace, goals, W=10, *, intents=None):
    """Label observed stalls using pre-decision intentions at the stall start.

    intents is {t: {agent_id: next_cell}}, saved separately from frozen records.
    Full positions are used only OFFLINE to identify a potential blocker. Inbox
    membership then gives 'epistemic' or 'rule_failure'. These are diagnostic
    labels, not a causal proof; one-hop delivery cannot guarantee resolution.
    Without an identifiable blocker (or saved intentions), report 'unattributed'
    instead of inventing an epistemic failure. Missing diagnostic data stays
    distinguishable from an actually empty inbox.
    """
    causes = {}
    for i in sorted(deadlocked_agents(trace, goals, W)):
        t = stall_start(trace, i, goals, W)
        row = trace[t]
        claims = (intents or {}).get(t, {})
        if i not in claims or tuple(claims[i]) == tuple(row.positions[i]):
            causes[i] = "unattributed"
            continue
        neighbours = [Message(j, tuple(row.positions[j]), tuple(goals[j]),
                              [tuple(next_cell)], sent_at=t)
                      for j, next_cell in claims.items() if j != i
                      and first_arrival(trace[:t + 1], j, goals) is None]
        blocker = blocking_neighbour(i, tuple(row.positions[i]), tuple(claims[i]), neighbours)
        causes[i] = ("unattributed" if blocker is None else
                     "rule_failure" if blocker in row.inbox_senders.get(i, []) else "epistemic")
    return causes
