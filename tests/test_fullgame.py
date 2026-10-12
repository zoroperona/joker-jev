from collections import Counter
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from joker_jev.agents.base import RandomAgent
from joker_jev.agents.typesafe import TypeSafeError
from joker_jev.core.engine import play
from joker_jev.core.models import Decision
from joker_jev.games.doudizhu.environment import EndgameGame
from joker_jev.games.doudizhu.episode import run_episode
from joker_jev.games.doudizhu.fullgame import run_suite
from joker_jev.games.doudizhu.heldout import make_cases, manifest
from joker_jev.games.doudizhu.scenarios import position
from joker_jev.games.doudizhu.strategy import DECK, SEATS


class RecordingBackend:
    def __init__(self):
        self.requests = []

    def evaluate(self, state, questions):
        self.requests.append(state)
        if "action" in questions:
            ids = questions["action"]["criteria"]
            chosen = next(iter(ids))
            answers = {"action": {"type": "choice", "choice": chosen, "confidence": 1.0,
                                  "probabilities": {i: float(i == chosen) for i in ids}}}
        else:
            answers = {k: {"type": "noul", "noul": 0.5} for k in questions}
        return {"model": "test", "answers": answers, "usage": {"input_tokens": 5, "output_tokens": 1}}


class FullgameTests(unittest.TestCase):
    def test_general_engine_and_terminal_shared_rewards(self):
        game = EndgameGame(position(("K K", "A", "3 4"), 1))
        result = play(game, {p: RandomAgent(3) for p in SEATS})
        self.assertEqual(result.turns, 1)
        self.assertEqual(result.rewards, {"landlord": -1.0, "farmer_after": 1.0, "farmer_before": 1.0})

    def test_observer_mutations_cannot_change_game_results(self):
        game = EndgameGame(position(("K K", "A", "3 4"), 1))
        def observer(step):
            step["rewards"].clear()
            step["cumulative_rewards"].clear()
            step["events"][0].data.clear()
        result = play(game, {p: RandomAgent(3) for p in SEATS}, on_step=observer)
        self.assertEqual(result.rewards["farmer_after"], 1)
        self.assertEqual(result.history[0].data["cards"], ["A"])

    def test_repeated_turns_history_card_counts_and_no_other_hands(self):
        initial = position(("K A 2", "3 4 5", "7 8 9"), 0)
        backend = RecordingBackend()
        result = run_episode(initial, "current_jev", "landlord", backend=backend)
        self.assertEqual(result["status"], "completed")
        focal = [t for t in result["trace"] if t["player"] == "landlord"]
        self.assertGreater(len(focal), 1)
        self.assertGreater(len(backend.requests), 2)
        played = DECK - Counter(c for h in initial.hands for c in h)
        actual_hands = [list(h) for h in initial.hands]
        past_events = []
        for row in result["trace"]:
            view = row["visible_state"]
            actor = SEATS.index(row["player"])
            self.assertEqual(view["self"]["hand"], actual_hands[actor])
            self.assertEqual(Counter(view["public"]["played_counts"]), played)
            self.assertEqual(view["public"]["history"], past_events)
            self.assertNotIn("hands", view)
            self.assertNotIn("manifest", view)
            unseen = DECK - played - Counter(actual_hands[actor])
            self.assertEqual(Counter(view["belief"]["facts"]["unseen_card_counts"]), unseen)
            for event in row["public_events"]:
                if event["kind"] == "move":
                    for card in event["data"]["cards"]:
                        actual_hands[actor].remove(card)
                        played[card] += 1
            past_events.extend(row["public_events"])

    def test_simulation_replans_on_each_nonforced_focal_turn(self):
        from joker_jev.games.doudizhu.rollout import score_actions
        with patch("joker_jev.games.doudizhu.episode.score_actions", wraps=score_actions) as scored:
            result = run_episode(position(("K A 2", "3 4 5", "7 8 9"), 0), "simulation", "landlord")
        decisions = [t for t in result["trace"] if t["player"] == "landlord" and not t["decision"].get("forced")]
        self.assertEqual(scored.call_count, len(decisions))
        self.assertGreater(scored.call_count, 1)

    def test_partial_api_failure_preserves_successful_call_usage_not_loss(self):
        class FailSecond(RecordingBackend):
            def evaluate(self, state, questions):
                if self.requests:
                    raise TypeSafeError("测试超时")
                return super().evaluate(state, questions)
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "episode.json"
            result = run_episode(position(("K A 2", "3 4 5", "7 8 9"), 0), "current_jev", "landlord",
                                 backend=FailSecond(), output=filename)
            self.assertEqual(result["status"], "api_error")
            self.assertIsNone(result["team_reward"])
            self.assertEqual(result["api_ledger"][0]["usage"]["input_tokens"], 5)
            self.assertEqual(result["api_ledger"][1]["status"], "api_error")
            self.assertEqual(json.loads(filename.read_text())["status"], "api_error")

    def test_turn_cap_is_not_a_loss_or_completed_game(self):
        result = run_episode(position(("K A 2", "3 4 5", "7 8 9"), 0), "simulation", "landlord", max_turns=1)
        self.assertEqual(result["status"], "turn_limit")
        self.assertIsNone(result["team_reward"])

    def test_illegal_action_is_saved_as_implementation_error_and_raised(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "error.json"
            with patch("joker_jev.games.doudizhu.episode.ReplanningAgent.decide", return_value=Decision("illegal")):
                with self.assertRaises(ValueError):
                    run_episode(position(("K A 2", "3 4 5", "7 8 9"), 0), "simulation", "landlord", output=path)
            saved = json.loads(path.read_text())
            self.assertEqual(saved["status"], "implementation_error")
            self.assertIsNone(saved["team_reward"])

    def test_manifest_is_deterministic_and_has_no_action_labels(self):
        a, b = make_cases(77, 2), make_cases(77, 2)
        self.assertEqual(manifest(a, 77), manifest(b, 77))
        self.assertNotEqual(manifest(a, 77)["sha256"], manifest(make_cases(78, 2), 78)["sha256"])
        self.assertNotIn("preferred", json.dumps(manifest(a, 77)))

    def test_balanced_profiles_and_seeds_match_local_and_live(self):
        with tempfile.TemporaryDirectory() as directory:
            local = run_suite(Path(directory) / "local.json", count=2, seed=123, balanced=True)
            live = run_suite(Path(directory) / "live.json", RecordingBackend, count=2, seed=123, balanced=True)
            self.assertEqual(local["manifest"], live["manifest"])
            self.assertEqual(local["settings"], live["settings"])
            self.assertEqual(len(live["episodes"]), 18)
            self.assertEqual(live["summary"]["paired_complete"]["setting_count"], 6)
            self.assertEqual({e["landlord_style"] for e in live["episodes"]},
                             {"random", "pressure", "conservative", "cooperative"})
            for e in live["episodes"]:
                self.assertEqual(e["status"], "completed")
                for seat, policy in e["policy_by_seat"].items():
                    self.assertEqual(policy, e["arm"] if seat == e["focal_seat"] else e["profile"])

    def test_report_checks_matched_local_results_and_counts_only_applied_actions(self):
        from joker_jev.games.doudizhu.report import render, behavior_counts
        with tempfile.TemporaryDirectory() as directory:
            local_path, live_path = Path(directory) / "local.json", Path(directory) / "live.json"
            local = run_suite(local_path, count=1, seed=123, balanced=True)
            live = run_suite(live_path, RecordingBackend, count=1, seed=123, balanced=True)
            rendered = render(live_path, local_path)
            self.assertIn("逐设置纯模拟终局收益完全一致", rendered)
            e = json.loads((live_path.parent / live['episodes'][0]['trace_path']).read_text())
            c = behavior_counts([e])
            self.assertEqual(c['applied_decisions'], sum(t['player'] == e['focal_seat'] and t['status'] == 'applied' for t in e['trace']))
            self.assertEqual(c['applied_decisions'], c.get('forced', 0) + c.get('nonforced', 0))
            local['episodes'][0]['team_reward'] *= -1
            local_path.write_text(json.dumps(local))
            with self.assertRaisesRegex(ValueError, "纯模拟结果不一致"):
                render(live_path, local_path)

    def test_conservative_preserves_pair_and_yields_to_teammate(self):
        import random
        from joker_jev.games.doudizhu.rollout import policy_action
        from joker_jev.games.doudizhu.strategy import player_state
        view = player_state(position(("3 3 K", "4 5", "6 7"), 0))
        chosen = policy_action(view, "conservative", random.Random(0))
        action = next(a for a in view["legal_actions"] if a["id"] == chosen)
        self.assertFalse(action["payload"]["breaks_pair"])
        initial = position(("4 5", "6 7", "8 9"), 1).advance(("6",))
        self.assertEqual(policy_action(player_state(initial), "conservative", random.Random(0)), "pass")

    def test_complete_suite_has_matched_seat_style_settings_and_independent_backends(self):
        created = []
        def factory():
            backend = RecordingBackend()
            created.append(backend)
            return backend
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "suite.json"
            report = run_suite(output, factory, count=1, seed=77, workers=2)
            self.assertEqual(len(report["episodes"]), 18)
            self.assertEqual(len(created), 12)
            self.assertEqual(report["summary"]["paired_complete"]["setting_count"], 6)
            groups = {}
            for e in report["episodes"]:
                groups.setdefault((e["case_id"], e["focal_seat"], e["farmer_style"]), set()).add(e["seed"])
                self.assertTrue((output.parent / e["trace_path"]).exists())
            self.assertTrue(all(len(v) == 1 for v in groups.values()))
            with self.assertRaises(ValueError):
                run_suite(output, factory, count=1, seed=77)


if __name__ == "__main__":
    unittest.main()
