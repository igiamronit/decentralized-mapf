
import unittest
from types import SimpleNamespace
import json
from decentralized_mapf.interfaces import Message
from decentralized_mapf.e5_consensus import ConsensusTracker


def message(sender, position, next_cells, sent_at, recipient=None, goal=None):
    return SimpleNamespace(
        sender=sender,
        position=position,
        goal=goal if goal is not None else position,
        next_cells=next_cells,
        sent_at=sent_at,
        recipient=recipient,
    )


class TestE5Consensus(unittest.TestCase):

    def setUp(self):
        self.tracker = ConsensusTracker()

    def round_data(self, t, claims, inboxes=None, active=None):
        if active is None:
            active = set(claims.keys())

        positions = {
            i: m.position for i, m in claims.items()
        }
        arrived = [
            m for inbox in (inboxes or {}).values() for m in inbox
        ]

        self.tracker.record_round(
            t=t,
            positions=positions,
            active=active,
            broadcasts=claims,
            inboxes=inboxes or {},
        )

    def test_same_round_mutual_receipt_is_zero(self):
        claims = {
            0: message(0, (0, 0), [(0, 1)], 0),
            1: message(1, (0, 2), [(0, 1)], 0),
        }
        inboxes = {
            0: [message(1, (0, 2), [(0, 1)], 0, recipient=0)],
            1: [message(0, (0, 0), [(0, 1)], 0, recipient=1)],
        }
        self.round_data(0, claims, inboxes)
        self.tracker.finalize(1)

        result = self.tracker.summary()
        self.assertEqual(result["n_conflicts"], 1)
        self.assertEqual(result["n_agreed"], 1)
        self.assertEqual(result["mean_rounds_to_agreement"], 0)

    def test_one_way_delivery_is_not_agreement(self):
        claims = {
            0: message(0, (0, 0), [(0, 1)], 0),
            1: message(1, (0, 2), [(0, 1)], 0),
        }
        inboxes = {
            0: [message(1, (0, 2), [(0, 1)], 0, recipient=0)]
        }
        self.round_data(0, claims, inboxes)
        self.tracker.finalize(1)

        result = self.tracker.summary()
        self.assertEqual(result["n_agreed"], 0)
        self.assertEqual(result["n_censored"], 1)

    def test_stale_delivery_is_not_agreement(self):
        claims = {
            0: message(0, (0, 0), [(0, 1)], 1),
            1: message(1, (0, 2), [(0, 1)], 1),
        }
        inboxes = {
            0: [message(1, (0, 2), [(0, 1)], 0, recipient=0)],
            1: [message(0, (0, 0), [(0, 1)], 1, recipient=1)],
        }
        self.round_data(1, claims, inboxes)
        self.tracker.finalize(2)

        self.assertEqual(self.tracker.summary()["n_agreed"], 0)

    def test_next_round_receipt_has_duration_one(self):
        claims0 = {
            0: message(0, (0, 0), [(0, 1)], 0),
            1: message(1, (0, 2), [(0, 1)], 0),
        }
        claims1 = {
            0: message(0, (0, 0), [(0, 1)], 1),
            1: message(1, (0, 2), [(0, 1)], 1),
        }
        self.round_data(0, claims0)
        inboxes = {
            0: [message(1, (0, 2), [(0, 1)], 1, recipient=0)],
            1: [message(0, (0, 0), [(0, 1)], 1, recipient=1)],
        }
        self.round_data(1, claims1, inboxes)
        self.tracker.finalize(2)

        self.assertEqual(
            self.tracker.summary()["mean_rounds_to_agreement"], 1
        )

    def test_conflict_ending_without_receipt(self):
        self.round_data(0, {
            0: message(0, (0, 0), [(0, 1)], 0),
            1: message(1, (0, 2), [(0, 1)], 0),
        })
        self.round_data(1, {
            0: message(0, (0, 0), [(0, 0)], 1),
            1: message(1, (0, 2), [(0, 2)], 1),
        })
        self.tracker.finalize(2)

        result = self.tracker.summary()
        self.assertEqual(result["n_ended_without_agreement"], 1)
        self.assertEqual(result["n_censored"], 0)

    def test_continuous_conflict_preserves_episode_start(self):
        for t in range(3):
            self.round_data(t, {
                0: message(0, (0, 0), [(0, 1)], t),
                1: message(1, (0, 2), [(0, 1)], t),
            })
        self.tracker.finalize(3)

        episodes = self.tracker.summary()["episodes"]
        self.assertEqual(len(episodes), 1)
        self.assertEqual(episodes[0]["t_start"], 0)

    def test_recurrence_creates_new_episode(self):
        self.round_data(0, {
            0: message(0, (0, 0), [(0, 1)], 0),
            1: message(1, (0, 2), [(0, 1)], 0),
        })
        self.round_data(1, {
            0: message(0, (0, 0), [(0, 0)], 1),
            1: message(1, (0, 2), [(0, 2)], 1),
        })
        self.round_data(2, {
            0: message(0, (0, 0), [(0, 1)], 2),
            1: message(1, (0, 2), [(0, 1)], 2),
        })
        self.tracker.finalize(3)

        episodes = self.tracker.summary()["episodes"]
        self.assertEqual(len(episodes), 2)
        self.assertEqual(
            [e["sequence"] for e in episodes], [1, 2]
        )

    def test_three_agents_same_destination_make_three_pairs(self):
        claims = {
            0: message(0, (0, 0), [(1, 1)], 0),
            1: message(1, (0, 1), [(1, 1)], 0),
            2: message(2, (0, 2), [(1, 1)], 0),
        }
        self.round_data(0, claims)
        self.tracker.finalize(1)

        self.assertEqual(self.tracker.summary()["n_conflicts"], 3)

    def test_no_conflicts_has_empty_aggregates(self):
        self.round_data(0, {
            0: message(0, (0, 0), [(0, 0)], 0),
            1: message(1, (0, 2), [(0, 2)], 0),
        })
        self.tracker.finalize(1)

        result = self.tracker.summary()
        self.assertEqual(result["n_conflicts"], 0)
        self.assertIsNone(result["mean_rounds_to_agreement"])
        self.assertIsNone(result["max_rounds_to_agreement"])
        self.assertIsNone(result["agreement_coverage"])


    def test_json_style_roundtrip(self):
        self.round_data(0, {
            0: message(0, (0, 0), [(0, 1)], 0),
            1: message(1, (0, 2), [(0, 1)], 0),
        })
        self.tracker.finalize(1)

        serialized = json.dumps(self.tracker.to_data())
        restored = ConsensusTracker.from_data(json.loads(serialized))

        self.assertEqual(
            restored.summary(), self.tracker.summary()
        )


    def test_inactive_agent_ends_episode(self):
        self.round_data(0, {
            0: message(0, (0, 0), [(0, 1)], 0),
            1: message(1, (0, 2), [(0, 1)], 0),
        })
        self.round_data(1, {
            0: message(0, (0, 0), [(0, 1)], 1),
        }, active={0})
        self.tracker.finalize(2)

        result = self.tracker.summary()
        self.assertEqual(result["n_ended_without_agreement"], 1)
        self.assertEqual(result["n_censored"], 0)

    def test_head_on_swap_is_a_conflict(self):
        self.round_data(0, {
            0: message(0, (0, 0), [(0, 1)], 0),
            1: message(1, (0, 1), [(0, 0)], 0),
        })
        self.tracker.finalize(1)

        self.assertEqual(self.tracker.summary()["n_conflicts"], 1)

    def test_stationary_occupant_is_conflict_when_targeted(self):
        self.round_data(0, {
            0: message(0, (0, 0), [(0, 1)], 0),
            1: message(1, (0, 1), [(0, 1)], 0),
        })
        self.tracker.finalize(1)

        self.assertEqual(self.tracker.summary()["n_conflicts"], 1)

    def test_empty_next_cells_means_current_position(self):
        self.round_data(0, {
            0: message(0, (0, 0), [], 0),
            1: message(1, (0, 1), [(0, 0)], 0),
        })
        self.tracker.finalize(1)

        self.assertEqual(self.tracker.summary()["n_conflicts"], 1)

    def test_persistent_conflict_after_agreement_is_one_episode(self):
        for t in range(3):
            claims = {
                0: message(0, (0, 0), [(0, 1)], t),
                1: message(1, (0, 2), [(0, 1)], t),
            }
            inboxes = {}
            if t == 0:
                inboxes = {
                    0: [message(1, (0, 2), [(0, 1)], 0, recipient=0)],
                    1: [message(0, (0, 0), [(0, 1)], 0, recipient=1)],
                }
            self.round_data(t, claims, inboxes)

        self.tracker.finalize(3)
        result = self.tracker.summary()
        self.assertEqual(result["n_conflicts"], 1)
        self.assertEqual(result["n_agreed"], 1)
        self.assertEqual(result["episodes"][0]["duration"], 0)

    def test_round_evidence_captures_claims_and_actual_deliveries(self):
        claims = {
            0: message(0, (0, 0), [(0, 1), (0, 2)], 0, goal=(0, 3)),
            1: message(1, (0, 2), [(0, 1)], 0, goal=(0, 0)),
        }
        inboxes = {
            0: [
                message(
                    1, (0, 2), [(0, 1)], 0,
                    recipient=0, goal=(0, 0)
                )
            ],
            1: [
                message(
                    0, (0, 0), [(0, 1), (0, 2)], 0,
                    recipient=1, goal=(0, 3)
                )
            ],
        }

        self.round_data(0, claims, inboxes)
        self.tracker.finalize(1)

        rounds = self.tracker.to_data()["rounds"]
        self.assertEqual(len(rounds), 1)

        record = rounds[0]
        self.assertEqual(record["t"], 0)
        self.assertEqual(record["active"], [0, 1])

        self.assertEqual(
            record["claims"]["0"],
            {
                "sender": 0,
                "position": [0, 0],
                "goal": [0, 3],
                "next_cells": [[0, 1], [0, 2]],
                "sent_at": 0,
            },
        )

        self.assertEqual(len(record["deliveries"]), 2)
        self.assertEqual(
            {
                (item["sender"], item["recipient"])
                for item in record["deliveries"]
            },
            {(0, 1), (1, 0)},
        )

    def test_round_evidence_survives_json_roundtrip(self):
        claims = {
            0: message(0, (0, 0), [(0, 1)], 0),
            1: message(1, (0, 2), [(0, 1)], 0),
        }
        inboxes = {
            0: [message(1, (0, 2), [(0, 1)], 0, recipient=0)],
            1: [message(0, (0, 0), [(0, 1)], 0, recipient=1)],
        }

        self.round_data(0, claims, inboxes)
        self.tracker.finalize(1)

        restored = ConsensusTracker.from_data(
            json.loads(json.dumps(self.tracker.to_data()))
        )

        self.assertEqual(restored.rounds, self.tracker.rounds)
        self.assertEqual(restored.summary(), self.tracker.summary())

    def test_finalize_censors_open_episode_without_agreement(self):
        tracker = ConsensusTracker()

        positions = [(0, 0), (0, 2)]
        active = [0, 1]

        broadcasts = {
            0: Message(
                sender=0,
                position=(0, 0),
                goal=(0, 2),
                next_cells=[(0, 1)],
                sent_at=0,
            ),
            1: Message(
                sender=1,
                position=(0, 2),
                goal=(0, 0),
                next_cells=[(0, 1)],
                sent_at=0,
            ),
        }

        tracker.record_round(
            t=0,
            positions=positions,
            active=active,
            broadcasts=broadcasts,
            inboxes={0: [], 1: []},
        )

        tracker.finalize(1)

        summary = tracker.summary()

        assert summary["n_conflicts"] == 1
        assert summary["n_agreed"] == 0
        assert summary["n_ended_without_agreement"] == 0
        assert summary["n_censored"] == 1
        assert summary["agreement_coverage"] == 0.0

        episode = summary["episodes"][0]
        assert episode["outcome"] == "censored_at_end"
        assert episode["t_start"] == 0
        assert episode["t_agreement"] is None
        assert episode["duration"] is None
        assert episode["observation_limit"] == 1

if __name__ == "__main__":
    unittest.main()