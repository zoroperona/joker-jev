from copy import deepcopy
from dataclasses import replace
import json
import unittest

from joker_jev.agents.typesafe import TypeSafeError
from joker_jev.games.doudizhu.evaluate import evaluate
from joker_jev.games.doudizhu.scenarios import SCENARIOS, position
from joker_jev.games.doudizhu.strategy import (
    action_id, infer_unseen, landlord_wins, min_plays, moves, oracle_actions,
    ordered, player_state,
)
from joker_jev.games.doudizhu.tactics import QUESTIONS, decide
from collections import Counter


class FakeBackend:
    def __init__(self, action):
        self.action = action
        self.requests = []

    def evaluate(self, state, questions):
        self.requests.append(deepcopy((state, questions)))
        if "action" in questions:
            ids = questions["action"]["criteria"]
            answers = {"action": {"type": "choice", "choice": self.action,
                                  "probabilities": {a: float(a == self.action) for a in ids},
                                  "confidence": 1.0}}
        else:
            answers = {key: {"type": "noul", "noul": 0.5} for key in questions}
        return {"answers": answers, "model": "test", "usage": {}}


class DoudizhuTests(unittest.TestCase):
    def test_all_scenarios_valid_and_reference_actions_legal(self):
        for case in SCENARIOS:
            with self.subTest(case=case.id):
                state = player_state(case.position)
                self.assertTrue(set(case.preferred) <= {a["id"] for a in state["legal_actions"]})
                json.dumps(state, allow_nan=False)

    def test_two_passes_restore_owner_and_force_lead(self):
        state = position(("K", "3 4", "6 6 A"), 1, "10", 0)
        one_pass = state.advance(())
        two_passes = one_pass.advance(())
        self.assertEqual(two_passes.actor, 0)
        self.assertEqual(two_passes.target, ())
        self.assertNotIn((), moves(two_passes.hands[0]))

    def test_farmer_teammate_finishing_is_shared_win(self):
        state = position(("K K", "A", "3 4"), 1)
        terminal = state.advance(("A",))
        self.assertFalse(landlord_wins(terminal))
        self.assertTrue(landlord_wins(position(("7 7", "A", "2"), 0).advance(("7", "7"))))

    def test_rules_pair_rocket_and_no_short_straights(self):
        self.assertEqual(moves(("3", "3"), ("2",)), ((),))
        self.assertIn(("SJ", "BJ"), moves(("SJ", "BJ"), ("2", "2")))
        self.assertEqual(moves(("A", "2"), ("SJ", "BJ")), ((),))
        self.assertEqual(min_plays(ordered(("3", "3", "A", "A"))), 2)
        with self.assertRaises(ValueError):
            position(("3 3 3", "4", "5"), 0).validate()

    def test_same_visible_state_under_different_hidden_assignments(self):
        original = SCENARIOS[0].position
        alternative = replace(original, hands=(ordered(("3",)), ordered(("K", "4")), original.hands[2]))
        self.assertEqual(player_state(original), player_state(alternative))

    def test_uniform_estimate_counts_duplicate_card_instances(self):
        estimates = infer_unseen(Counter({"K": 2, "3": 1, "4": 1}), {"a": 2, "b": 2}, ())
        self.assertAlmostEqual(estimates["a"]["pair_hand_probability"], 1 / 6)
        self.assertAlmostEqual(estimates["b"]["pair_hand_probability"], 1 / 6)

    def test_control_retention_and_single_threat_have_different_leads(self):
        cases = {case.id: case for case in SCENARIOS}
        self.assertEqual(oracle_actions(cases["probe_pair_keep_control"].position), ("play:3", "play:Q"))
        self.assertEqual(oracle_actions(cases["single_threat_changes_lead"].position), ("play:A",))

    def test_two_stage_requests_never_receive_labels_or_full_hands(self):
        case = SCENARIOS[0]
        state = player_state(case.position)
        original = deepcopy(state)
        backend = FakeBackend(case.preferred[0])
        result = decide(state, backend)
        self.assertEqual(result["action_id"], case.preferred[0])
        self.assertEqual(len(backend.requests), 2)
        self.assertEqual(set(backend.requests[0][1]), set(QUESTIONS))
        self.assertIn("tactical_assessments", backend.requests[1][0])
        for request, _ in backend.requests:
            self.assertFalse({"position", "hands", "preferred", "rationale", "topic", "id"} & set(request))
            self.assertEqual(request["self"]["hand"], list(case.position.hands[case.position.actor]))
        self.assertEqual(state, original)

    def test_invalid_tactical_output_rejected(self):
        class BadBackend:
            def evaluate(self, state, questions):
                return {"answers": {k: {"type": "noul", "noul": float("nan")} for k in questions}}
        with self.assertRaises(TypeSafeError):
            decide(player_state(SCENARIOS[0].position), BadBackend())

    def test_offline_report_is_not_a_model_score(self):
        report = evaluate()
        self.assertEqual(report["summary"]["evaluated"], 0)
        self.assertEqual(report["summary"]["scenarios"], len(SCENARIOS))
        self.assertTrue(report["limitations"])


if __name__ == "__main__":
    unittest.main()
