from dataclasses import replace
import json
import unittest

from joker_jev.agents.base import Agent, RandomAgent
from joker_jev.agents.jev import JEVAgent
from joker_jev.core.engine import play
from joker_jev.core.game import CardGame, CardInference, Transition
from joker_jev.core.models import (
    Action, Belief, Decision, DecisionContext, GameRules, Observation, PlayerView, RewardRule,
)
from joker_jev.games.high_card.game import HighCardGame, HighCardState
from joker_jev.games.high_card.inference import HighCardInference


class FixedAgent(Agent):
    def __init__(self, action_id):
        self.action_id = action_id

    def decide(self, context):
        return Decision(self.action_id)


class EmptyInference(CardInference):
    def infer(self, observation):
        return Belief({}, {}, ("此测试环境没有隐藏信息",))


class OneMoveGame(CardGame[int]):
    """不同状态类型、玩家数量、动作和奖励的环境，验证引擎不依赖比牌。"""

    @property
    def rules(self):
        return GameRules("one_move", "协议测试", "1", ("solo",), "取牌", (), (),
                         (RewardRule("取牌", "solo", 2.0, "取牌奖励"),), "取牌结束")

    def initial_state(self, seed):
        return 0

    def current_player(self, state):
        return "solo"

    def view(self, state, player_id):
        return PlayerView({}, {"remaining": 1 - state})

    def legal_actions(self, state):
        return (Action("take", "取牌"),)

    def step(self, state, action):
        return Transition(1, (), {"solo": 2.0})

    def is_terminal(self, state):
        return state == 1

    def create_inference(self):
        return EmptyInference()


class FrameworkTests(unittest.TestCase):
    def setUp(self):
        self.game = HighCardGame()

    def context(self):
        state = self.game.initial_state(4)
        view = self.game.view(state, "p0")
        obs = Observation("high_card", "p0", 0, view.private, view.public,
                          self.game.legal_actions(state), ())
        return DecisionContext(self.game.rules, obs, HighCardInference().infer(obs), 0.0)

    def test_trick_winner_leads_and_rewards_are_incremental(self):
        state = HighCardState(((1, 5, 8), (2, 3, 6)), "p0")
        first = self.game.step(state, Action("play:5", "出 5", {"card": 5}))
        self.assertEqual(first.rewards, {"p0": 0.0, "p1": 0.0})
        self.assertEqual(first.state.current, "p1")
        second = self.game.step(first.state, Action("play:6", "出 6", {"card": 6}))
        self.assertEqual(second.rewards, {"p0": -1.0, "p1": 1.0})
        self.assertEqual(second.state.scores, (0, 1))
        self.assertEqual(second.state.current, "p1")
        self.assertEqual(second.state.trick, ())
        self.assertEqual(state.hands, ((1, 5, 8), (2, 3, 6)))

    def test_seeded_episodes_conserve_cards_and_rewards(self):
        for seed in range(100):
            def run():
                return play(self.game, {"p0": RandomAgent(10), "p1": RandomAgent(20)}, seed)
            result = run()
            self.assertEqual(result, run())
            self.assertEqual(result.turns, 6)
            cards = [e.data["card"] for e in result.history if e.kind == "card_played"]
            self.assertEqual(len(cards), 6)
            self.assertEqual(len(set(cards)), 6)
            scores = result.history[-1].data["scores"]
            self.assertEqual(sum(scores.values()), 3)
            self.assertEqual(sum(result.rewards.values()), 0)
            for player in scores:
                self.assertEqual(result.rewards[player], 2 * scores[player] - 3)

    def test_hidden_hands_do_not_change_player_view_or_belief(self):
        state = HighCardState(((1, 5, 8), (2, 3, 6)), "p0")
        other_world = replace(state, hands=(state.hands[0], (2, 4, 7)))
        self.assertEqual(self.game.view(state, "p0"), self.game.view(other_world, "p0"))
        self.assertEqual(self.game.legal_actions(state), self.game.legal_actions(other_world))
        beliefs = []
        for world in (state, other_world):
            view = self.game.view(world, "p0")
            obs = Observation("high_card", "p0", 0, view.private, view.public,
                              self.game.legal_actions(world), ())
            beliefs.append(HighCardInference().infer(obs))
        self.assertEqual(beliefs[0], beliefs[1])
        context = self.context()
        self.assertNotIn("seed", context.observation.public)
        self.assertEqual(set(context.observation.private), {"hand"})

    def test_inference_tracks_public_cards_and_marginal_probabilities(self):
        state = HighCardState(((1, 5, 8), (2, 3, 6)), "p0")
        transition = self.game.step(state, Action("play:5", "出 5", {"card": 5}))
        view = self.game.view(transition.state, "p1")
        obs = Observation("high_card", "p1", 1, view.private, view.public,
                          self.game.legal_actions(transition.state), transition.events)
        belief = HighCardInference().infer(obs)
        self.assertEqual(belief.facts["played_cards"], [5])
        self.assertEqual(belief.facts["unseen_cards"], [1, 4, 7, 8])
        probabilities = belief.estimates["opponent_card_probability"]
        self.assertEqual(probabilities, {"1": 0.5, "4": 0.5, "7": 0.5, "8": 0.5})
        self.assertEqual(sum(probabilities.values()), 2)

    def test_engine_reuses_protocol_for_another_game(self):
        result = play(OneMoveGame(), {"solo": FixedAgent("take")})
        self.assertEqual(result.turns, 1)
        self.assertEqual(result.rewards, {"solo": 2.0})

    def test_invalid_agent_action_and_missing_player_fail(self):
        with self.assertRaisesRegex(ValueError, "合法"):
            play(self.game, {"p0": FixedAgent("play:99"), "p1": RandomAgent()})
        with self.assertRaisesRegex(ValueError, "每个玩家"):
            play(self.game, {"p0": RandomAgent()})

    def test_turn_limit_does_not_report_a_completed_game(self):
        with self.assertRaisesRegex(RuntimeError, "max_turns"):
            play(self.game, {"p0": RandomAgent(), "p1": RandomAgent()}, max_turns=1)

    def test_observation_mutation_cannot_modify_game_or_history(self):
        class MutatingAgent(Agent):
            def decide(self, context):
                action = context.observation.legal_actions[0]
                context.observation.private["hand"].clear()
                context.observation.public["deck"].clear()
                action.payload["card"] = 99
                for event in context.observation.history:
                    event.data.clear()
                return Decision(action.id)

        result = play(self.game, {"p0": MutatingAgent(), "p1": MutatingAgent()})
        self.assertEqual(result.turns, 6)
        cards = [e.data["card"] for e in result.history if e.kind == "card_played"]
        self.assertTrue(all(1 <= card <= 8 for card in cards))

    def test_jev_receives_rules_rewards_and_beliefs(self):
        def backend(request):
            data = json.loads(request)
            context = data["context"]
            self.assertTrue(context["rules"]["rewards"])
            self.assertTrue(context["belief"]["assumptions"])
            self.assertEqual(context["protocol_version"], "1")
            return json.dumps({"action_id": context["observation"]["legal_actions"][0]["id"]})

        result = play(self.game, {"p0": JEVAgent(backend), "p1": RandomAgent()})
        self.assertEqual(result.turns, 6)

    def test_jev_rejects_malformed_and_illegal_responses(self):
        for response in ("garbage", "[]", "null", '{"action_id": 1}',
                         '{"action_id": "play:99"}', '{"action_id": "play:1", "reason": 7}'):
            with self.subTest(response=response), self.assertRaises(ValueError):
                JEVAgent(lambda request: response).decide(self.context())

    def test_invalid_game_rewards_fail(self):
        class BadRewardGame(OneMoveGame):
            def step(self, state, action):
                return Transition(1, (), {"solo": float("nan")})

        with self.assertRaisesRegex(ValueError, "有限数值"):
            play(BadRewardGame(), {"solo": FixedAgent("take")})


if __name__ == "__main__":
    unittest.main()
