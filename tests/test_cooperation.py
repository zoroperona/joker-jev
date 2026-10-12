from collections import Counter
from copy import deepcopy
from dataclasses import replace
from itertools import combinations
import json
from pathlib import Path
import tempfile
import unittest

from joker_jev.agents.typesafe import TypeSafeError
from joker_jev.games.doudizhu.compare import compare
from joker_jev.games.doudizhu.scenarios import COOPERATION_SCENARIOS, position
from joker_jev.games.doudizhu.strategy import SEATS, moves, oracle_actions, ordered, player_state


class ComparisonBackend:
    model = "test-fixed"

    def evaluate(self, state, questions):
        if "action" in questions:
            ids = questions["action"]["criteria"]
            selected = next(iter(ids))
            answers = {"action": {"type": "choice", "choice": selected, "confidence": 1.0,
                                  "probabilities": {key: float(key == selected) for key in ids}}}
        else:
            answers = {key: {"type": "noul", "noul": 0.5} for key in questions}
        return {"model": self.model, "answers": answers, "usage": {}}


class CooperationTests(unittest.TestCase):
    def test_variants_valid_and_reference_actions_legal(self):
        for case in COOPERATION_SCENARIOS:
            with self.subTest(case=case.id):
                case.position.validate()
                self.assertTrue(set(case.preferred) <= {a["id"] for a in player_state(case.position)["legal_actions"]})

    def test_ab_only_changes_control_facts(self):
        for case in COOPERATION_SCENARIOS:
            baseline = player_state(case.position)
            enhanced = player_state(case.position, True)
            del enhanced["belief"]["facts"]["control"]
            self.assertEqual(baseline, enhanced)

    def test_possibility_matches_all_compatible_hidden_assignments(self):
        for case in COOPERATION_SCENARIOS:
            pos = case.position
            state = player_state(pos, True)
            unseen = tuple(Counter(state["belief"]["facts"]["unseen_card_counts"]).elements())
            others = [i for i in range(3) if i != pos.actor]
            seen = {i: {"beat": False, "finish": False} for i in others}
            for selected in combinations(range(len(unseen)), len(pos.hands[others[0]])):
                selected = set(selected)
                hands = list(pos.hands)
                hands[others[0]] = ordered(c for j, c in enumerate(unseen) if j in selected)
                hands[others[1]] = ordered(c for j, c in enumerate(unseen) if j not in selected)
                alternative = replace(pos, hands=tuple(hands))
                self.assertEqual(state, player_state(alternative, True))
                for i in others:
                    responses = [c for c in moves(hands[i], pos.target) if c]
                    seen[i]["beat"] |= bool(responses)
                    seen[i]["finish"] |= any(len(c) == len(hands[i]) for c in responses)
            facts = state["belief"]["facts"]["control"]["response_possibilities"]
            for i in others:
                self.assertEqual(facts[SEATS[i]]["can_possibly_beat_active_play"], seen[i]["beat"])
                self.assertEqual(facts[SEATS[i]]["can_possibly_finish_by_beating_active_play"], seen[i]["finish"])

    def test_passing_landlord_may_have_high_card_but_cannot_reenter_closed_trick(self):
        case = next(c for c in COOPERATION_SCENARIOS if c.id == "higher_enemy_card_but_trick_closes")
        facts = player_state(case.position, True)["belief"]["facts"]["control"]
        self.assertTrue(facts["response_possibilities"]["landlord"]["can_possibly_beat_active_play"])
        self.assertTrue(facts["passing_ends_trick"])
        self.assertEqual(facts["responders_after_self_pass_before_owner_returns"], [])
        self.assertFalse(facts["opponent_can_possibly_finish_on_current_play_after_self_pass"])
        # 接管后重新开始响应，先前过牌的地主仍可响应。
        after = case.position.advance(("2",))
        self.assertEqual(after.passes, 0)

    def test_rocket_requires_two_cards_in_one_hand(self):
        pos = position(("SJ", "BJ", "3 A"), 2, "K K", 1)
        facts = player_state(pos, True)["belief"]["facts"]["control"]
        self.assertFalse(facts["response_possibilities"]["landlord"]["can_possibly_beat_active_play"])

    def test_free_lead_has_no_active_play_threat(self):
        state = player_state(position(("3", "4", "5"), 2), True)
        self.assertEqual(state["belief"]["facts"]["control"], {"active_play_exists": False})

    def test_comparison_persists_and_refuses_to_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            report = compare(ComparisonBackend(), repeats=1, output=str(path))
            self.assertEqual(report["status"], "completed")
            self.assertEqual(len(report["trials"]), 2 * len(COOPERATION_SCENARIOS))
            self.assertEqual(json.loads(path.read_text())["summary"], report["summary"])
            for arm in ("baseline", "control_facts"):
                self.assertEqual(report["summary"][arm]["completed"], len(COOPERATION_SCENARIOS))
            with self.assertRaisesRegex(ValueError, "已存在"):
                compare(ComparisonBackend(), output=str(path))

    def test_errors_are_recorded_not_counted_as_successful_decisions(self):
        class FailureBackend(ComparisonBackend):
            def evaluate(self, state, questions):
                raise TypeSafeError("模拟服务错误")
        report = compare(FailureBackend(), repeats=1)
        self.assertEqual(report["status"], "completed_with_errors")
        self.assertEqual(report["summary"]["baseline"]["completed"], 0)
        self.assertEqual(report["summary"]["baseline"]["errors"], len(COOPERATION_SCENARIOS))


if __name__ == "__main__":
    unittest.main()
