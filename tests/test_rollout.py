from dataclasses import replace
import random
import unittest
from unittest.mock import patch

from joker_jev.games.doudizhu.benchmark import benchmark, paired_summary
from joker_jev.games.doudizhu.evaluate import evaluate
from joker_jev.games.doudizhu.rollout import (
    compatible_worlds, policy_action, score_actions, choose_hybrid, simulate,
)
from joker_jev.games.doudizhu.scenarios import SCENARIOS, position
from joker_jev.games.doudizhu.strategy import player_state


class LegalButDifferentBackend:
    model = "fixture"

    def __init__(self):
        self.states = []

    def evaluate(self, state, questions):
        self.states.append(state)
        if "action" not in questions:
            return {"answers": {k: {"type": "noul", "noul": 0.5} for k in questions}}
        ids = questions["action"]["criteria"]
        choice = next(a for a in ids if a != "pass")
        return {"model": self.model, "answers": {"action": {
            "type": "choice", "choice": choice, "confidence": 1.0,
            "probabilities": {a: float(a == choice) for a in ids},
        }}, "usage": {}}


class RolloutTests(unittest.TestCase):
    def test_hidden_worlds_preserve_duplicate_weights_and_view(self):
        pos = position(("K", "K 3", "A 5"), 2)
        state = player_state(pos)
        worlds = compatible_worlds(state)
        self.assertEqual(len(worlds), 2)
        self.assertAlmostEqual(sum(w for _, w in worlds), 1)
        weights = {p.hands[0]: w for p, w in worlds}
        self.assertAlmostEqual(weights[("K",)], 2 / 3)
        self.assertAlmostEqual(weights[("3",)], 1 / 3)
        for world, _ in worlds:
            self.assertEqual(player_state(world), state)

    def test_policies_and_plan_do_not_depend_on_actual_hidden_assignment(self):
        original = SCENARIOS[1].position
        swapped = replace(original, hands=(("4",), ("4", "Q"), original.hands[2]))
        a, b = player_state(original, True), player_state(swapped, True)
        self.assertEqual(a, b)
        for policy in ("cooperative", "greedy", "random", "pressure"):
            self.assertEqual(policy_action(a, policy, random.Random(3)), policy_action(b, policy, random.Random(3)))
        self.assertEqual(score_actions(a), score_actions(b))

    def test_rollouts_do_not_call_full_information_solver(self):
        with patch("joker_jev.games.doudizhu.strategy.landlord_wins", side_effect=AssertionError("oracle leak")):
            result = score_actions(player_state(SCENARIOS[1].position))
        for action in result["actions"]:
            for profile in action["by_continuation_policy"].values():
                self.assertAlmostEqual(profile["team_win_mass"] + profile["team_loss_mass"] + profile["truncated_mass"], 1)

    def test_terminal_team_reward_is_not_individual_finish_reward(self):
        pos = position(("Q", "4 4", "3 5 A"), 2, "K", 1)
        result = simulate(pos, "pass", "cooperative")
        self.assertEqual(result["reward"], 1)  # 队友出完 44，根玩家仍有三张。
        finish = position(("K K", "A", "3 4"), 1)
        self.assertEqual(simulate(finish, "play:A", "greedy", max_turns=1)["reward"], 1)

    def test_cutoff_preserves_uncertainty_instead_of_counting_a_loss(self):
        result = score_actions(player_state(SCENARIOS[1].position), max_turns=1)
        for action in result["actions"]:
            for p in action["by_continuation_policy"].values():
                self.assertEqual(p["truncated_mass"], 1)
                self.assertIsNone(p["expected_team_reward"])
                self.assertEqual((p["reward_lower_bound"], p["reward_upper_bound"]), (-1, 1))

    def test_hybrid_uses_aggregates_and_accepts_legal_disagreement(self):
        backend = LegalButDifferentBackend()
        state = player_state(SCENARIOS[1].position)
        result = choose_hybrid(state, score_actions(state), backend)
        self.assertEqual(result["action_id"], "play:A")
        sent = backend.states[0]
        self.assertIn("candidate_consequences", sent)
        self.assertNotIn("preferred", sent)
        self.assertNotIn("hands", sent)
        self.assertNotIn("full_information_winning_actions", sent)

    def test_strategy_disagreement_is_completed_experiment_not_error(self):
        report = benchmark(LegalButDifferentBackend(), cases=(SCENARIOS[1],))
        self.assertEqual(report["status"], "completed")
        for arm in ("current_jev", "simulation_jev"):
            self.assertEqual(report["summary"][arm]["execution_errors"], 0)
            self.assertEqual(report["summary"][arm]["human_reference_agreements"], 0)

    def test_reference_can_disagree_with_oracle_without_blocking_evaluation(self):
        case = replace(SCENARIOS[1], preferred=("play:A",))
        with patch("joker_jev.games.doudizhu.evaluate.SCENARIOS", (case,)):
            report = evaluate()
        self.assertFalse(report["scenarios"][0]["reference_subset_of_full_information_wins"])

    def test_incomplete_arm_does_not_enter_paired_comparison(self):
        report = benchmark(LegalButDifferentBackend(), cases=(SCENARIOS[1],))
        self.assertEqual(paired_summary(report["trials"], report["arms"])["complete_case_repetition_groups"], 1)
        trials = report["trials"][:-1]
        self.assertEqual(paired_summary(trials, report["arms"])["complete_case_repetition_groups"], 0)


if __name__ == "__main__":
    unittest.main()
