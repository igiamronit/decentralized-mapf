
"""Passive tracking of mutual current-round claim receipt (E5)."""

from collections import defaultdict
from collections.abc import Mapping
from copy import deepcopy


E5_DEFINITION = "mutual_current_claim_receipt_v1"


def _cell(value):
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError("A cell must be a (row, column) pair")
    if any(isinstance(v, bool) or not isinstance(v, int) for v in value):
        raise ValueError("Cell coordinates must be integers")
    return tuple(value)


def _claim_conflict(a, b):
    """Symmetric pairwise immediate-claim conflict predicate."""
    p_i, q_i = a["position"], a["next_cell"]
    p_j, q_j = b["position"], b["next_cell"]

    same_destination = (
        q_i == q_j and (q_i != p_i or q_j != p_j)
    )
    head_on_swap = (
        q_i == p_j and q_j == p_i
        and q_i != p_i and q_j != p_j
    )
    return same_destination or head_on_swap


class ConsensusTracker:
    """Track pairwise conflict episodes and mutual fresh-claim receipt.

    Call record_round once per nonterminal decision timestep, after delivery
    and before actions. Call finalize at the terminal trace timestamp.
    """

    def __init__(self):
        self.episodes = []
        self._open = {}
        self._sequence = defaultdict(int)
        self._finalized = False
        self._last_t = None
        self.rounds = []

    @staticmethod
    def _snapshot_claim(message, agent_id, t, position):
        if message.sender != agent_id:
            raise ValueError("Broadcast sender does not match its agent ID")
        if message.sent_at != t:
            raise ValueError("Broadcast timestamp does not match round")
        if _cell(message.position) != _cell(position):
            raise ValueError("Broadcast position does not match snapshot")

        next_cells = tuple(_cell(c) for c in (message.next_cells or []))
        return {
            "sender": message.sender,
            "position": _cell(message.position),
            "goal": _cell(message.goal),
            "next_cells": next_cells,
            "sent_at": message.sent_at,
            "next_cell": next_cells[0] if next_cells else _cell(message.position),
        }

    @staticmethod
    def _same_payload(message, claim):
        return (
            message.sender == claim["sender"]
            and _cell(message.position) == claim["position"]
            and _cell(message.goal) == claim["goal"]
            and tuple(_cell(c) for c in (message.next_cells or []))
                == claim["next_cells"]
            and message.sent_at == claim["sent_at"]
        )

    @staticmethod
    def _message_data(message, recipient=None):
        """Return a JSON-serializable snapshot of a delivered message."""
        return {
            "sender": message.sender,
            "recipient": (
                message.recipient if recipient is None else recipient
            ),
            "position": list(_cell(message.position)),
            "goal": list(_cell(message.goal)),
            "next_cells": [
                list(_cell(cell))
                for cell in (message.next_cells or [])
            ],
            "sent_at": message.sent_at,
        }

    def record_round(self, t, positions, active, broadcasts, inboxes):
        """Record claims and actual delivered inbox messages for one round.

        positions: {agent_id: (row, column)} or an ID-indexed position list.
        Mapping IDs may be nonconsecutive; finished robots need not be included.
        active: iterable of active agent IDs.
        broadcasts: {agent_id: Message} pre-recipient broadcasts.
        inboxes: {receiver_id: [Message, ...]} after channel delivery.
        """
        if self._finalized:
            raise ValueError("Cannot record after tracker finalization")
        if isinstance(t, bool) or not isinstance(t, int) or t < 0:
            raise ValueError("t must be a nonnegative integer")
        if self._last_t is not None and t != self._last_t + 1:
            raise ValueError("Decision rounds must have contiguous timestamps")

        if not isinstance(positions, Mapping):
            positions = dict(enumerate(positions))
        active_ids = set(active)
        if not set(broadcasts).issubset(active_ids):
            raise ValueError("A broadcast sender is not active")
        if set(broadcasts) != active_ids:
            raise ValueError("Every active agent must have one broadcast")
        if any(
            isinstance(i, bool)
            or not isinstance(i, int)
            or i < 0
            or i not in positions
            for i in broadcasts
        ):
            raise ValueError("A broadcast sender has no position snapshot")

        claims = {
            i: self._snapshot_claim(message, i, t, positions[i])
            for i, message in broadcasts.items()
        }

        # Preserve the exact pre-decision broadcasts and actual deliveries.
        # This is measurement-only and must never affect planner decisions.
        round_evidence = {
            "t": t,
            "active": sorted(active_ids),
            "claims": {
                str(agent_id): {
                    "sender": claim["sender"],
                    "position": list(claim["position"]),
                    "goal": list(claim["goal"]),
                    "next_cells": [
                        list(cell) for cell in claim["next_cells"]
                    ],
                    "sent_at": claim["sent_at"],
                }
                for agent_id, claim in claims.items()
            },
            "deliveries": [
                self._message_data(message, recipient=receiver)
                for receiver, messages in inboxes.items()
                for message in messages
            ],
        }
        self.rounds.append(round_evidence)

        current = {}
        ids = sorted(claims)
        for index, i in enumerate(ids):
            for j in ids[index + 1:]:
                if _claim_conflict(claims[i], claims[j]):
                    current[(i, j)] = (claims[i], claims[j])

        for pair in list(self._open):
            if pair not in current:
                episode = self._open.pop(pair)
                episode["ended_at"] = t
                episode["outcome"] = (
                    "agreed" if episode["t_agreement"] is not None
                    else "ended_without_agreement"
                )

        for pair, pair_claims in current.items():
            if pair not in self._open:
                self._sequence[pair] += 1
                episode = {
                    "agents": list(pair),
                    "sequence": self._sequence[pair],
                    "t_start": t,
                    "t_agreement": None,
                    "ended_at": None,
                    "observation_limit": None,
                    "duration": None,
                    "outcome": None,
                }
                self.episodes.append(episode)
                self._open[pair] = episode

            episode = self._open[pair]
            if episode["t_agreement"] is not None:
                continue

            i, j = pair
            claim_i, claim_j = pair_claims
            received_j = any(
                msg.recipient == i and msg.sender == j and msg.sent_at == t
                and self._same_payload(msg, claim_j)
                for msg in inboxes.get(i, [])
            )
            received_i = any(
                msg.recipient == j and msg.sender == i and msg.sent_at == t
                and self._same_payload(msg, claim_i)
                for msg in inboxes.get(j, [])
            )
            if received_i and received_j:
                episode["t_agreement"] = t
                episode["duration"] = t - episode["t_start"]
                episode["outcome"] = "agreed"

        self._last_t = t

    def finalize(self, terminal_t):
        """Censor episodes still open at the terminal trace timestamp."""
        if self._finalized:
            return
        if (
            isinstance(terminal_t, bool)
            or not isinstance(terminal_t, int)
            or terminal_t < 0
        ):
            raise ValueError("terminal_t must be an integer")
        if self._last_t is not None and terminal_t < self._last_t:
            raise ValueError("Terminal timestamp precedes the last round")

        for episode in self._open.values():
            episode["observation_limit"] = terminal_t
            if episode["t_agreement"] is None:
                episode["outcome"] = "censored_at_end"
            else:
                episode["outcome"] = "agreed"

        self._open.clear()
        self._finalized = True

    def summary(self):
        if not self._finalized:
            raise ValueError("Finalize the tracker before summarizing")

        agreed = [e for e in self.episodes if e["outcome"] == "agreed"]
        ended = [e for e in self.episodes
                 if e["outcome"] == "ended_without_agreement"]
        censored = [e for e in self.episodes
                    if e["outcome"] == "censored_at_end"]
        durations = [e["duration"] for e in agreed]

        n = len(self.episodes)
        return {
            "e5_definition": E5_DEFINITION,
            "n_conflicts": n,
            "n_agreed": len(agreed),
            "n_ended_without_agreement": len(ended),
            "n_censored": len(censored),
            "agreement_coverage": len(agreed) / n if n else None,
            "mean_rounds_to_agreement": (
                sum(durations) / len(durations) if durations else None
            ),
            "max_rounds_to_agreement": max(durations) if durations else None,
            "episodes": deepcopy(self.episodes),
        }

    def to_data(self):
        if not self._finalized:
            raise ValueError("Finalize the tracker before serialization")
        return {
            "e5_definition": E5_DEFINITION,
            "episodes": deepcopy(self.episodes),
            "rounds": deepcopy(self.rounds),
        }

    @classmethod
    def from_data(cls, data):
        if data.get("e5_definition") != E5_DEFINITION:
            raise ValueError("Unsupported E5 definition")

        tracker = cls()
        tracker.episodes = deepcopy(data["episodes"])
        tracker.rounds = deepcopy(data.get("rounds", []))
        for episode in tracker.episodes:
            pair = tuple(episode["agents"])
            tracker._sequence[pair] = max(
                tracker._sequence[pair], episode["sequence"]
            )
        tracker._finalized = True
        return tracker
