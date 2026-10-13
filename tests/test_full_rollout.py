from collections import Counter
from dataclasses import replace
import json
from pathlib import Path
import random
import tempfile
import unittest

from joker_jev.games.doudizhu.full.agents import FullSimpleAgent, SimulationJEVAgent
from joker_jev.games.doudizhu.full.cards import DECK, classify, ordered
from joker_jev.games.doudizhu.full.game import FullDoudizhuGame, PLAYERS, State
from joker_jev.games.doudizhu.full.rollout import (WorldSampler, evaluate_bidding, evaluate_plays,
                                                   rough_groups, simulate)
from test_full_doudizhu import context, take
from test_fullgame import RecordingBackend


class FullRolloutTests(unittest.TestCase):
    def test_fast_simulation_matches_engine_with_simple_agents(self):
        game = FullDoudizhuGame(); agent = FullSimpleAgent()
        for seed in range(25):
            state = take(game, game.initial_state(seed), 'bid:3').state
            expected = simulate(state.hands, state.actor, state.landlord, state.bid_score)
            while not game.is_terminal(state):
                decision = agent.decide(context(game, state))
                transition = game.step(state, next(a for a in game.legal_actions(state) if a.id == decision.action_id))
                state = transition.state
            self.assertEqual([transition.rewards[p] for p in PLAYERS], expected)

    def test_rough_groups_matches_simple_reference(self):
        self.assertEqual(rough_groups(ordered('3 4 5 6 7 8 8 9 9 10 10'.split())), 2)
        self.assertEqual(rough_groups(ordered('3 3 3 4 4 4 5 6'.split())), 3)
        self.assertEqual(rough_groups(()), 0)

    def test_sampled_worlds_respect_public_constraints(self):
        game = FullDoudizhuGame()
        state = take(game, take(game, game.initial_state(4), 'bid:3').state, game.legal_actions(
            take(game, game.initial_state(4), 'bid:3').state)[0].id).state
        ctx = context(game, state)
        sampler = WorldSampler(ctx)
        played = Counter(c for cards in state.played for c in cards)
        landlord_known = Counter(state.bottom) - Counter(state.played[state.landlord])
        rng = random.Random(1)
        for _ in range(20):
            hands, bottom = sampler.sample(rng)
            self.assertEqual(bottom, ())
            self.assertEqual([len(h) for h in hands], [len(h) for h in state.hands])
            self.assertEqual(hands[state.actor], state.hands[state.actor])
            self.assertEqual(Counter(c for h in hands for c in h) + played, Counter(DECK))
            if state.landlord != state.actor:
                self.assertFalse(landlord_known - Counter(hands[state.landlord]))

    def test_simulation_is_identical_under_hidden_reassignment(self):
        game = FullDoudizhuGame(); s = take(game, game.initial_state(0), 'bid:3').state
        other = replace(s, hands=(s.hands[0], s.hands[2], s.hands[1]), seed=123456)
        a, b = context(game, s), context(game, other)
        self.assertEqual(evaluate_plays(a, a.observation.legal_actions, 80),
                         evaluate_plays(b, b.observation.legal_actions, 80))
        bid = game.initial_state(7)
        swapped = replace(bid, hands=(bid.hands[0], bid.hands[2], bid.hands[1]), bottom=bid.bottom)
        if bid.actor == 0:
            self.assertEqual(evaluate_bidding(context(game, bid), 20), evaluate_bidding(context(game, swapped), 20))

    def test_v3_auto_finishes_and_bounds_choices(self):
        game = FullDoudizhuGame()
        finish = State((('Q', 'Q'), ('5', '6'), ('A', '2')), (), 0, phase='playing', landlord=0, bid_score=1)
        backend = RecordingBackend()
        self.assertEqual(SimulationJEVAgent(backend).decide(context(game, finish)).action_id, 'pair:9:1:Q,Q')
        self.assertEqual(backend.requests, [])
        hand = ordered('3 3 3 4 4 4 5 5 5 6 6 6 7 8 9 10 J Q K A'.split())
        state = State((hand, ('2',), ('SJ',)), (), 0, phase='playing', landlord=0, bid_score=1)
        ctx = context(game, state)
        class Backend(RecordingBackend):
            def evaluate(inner, state, questions):
                criteria = questions['action']['criteria']
                self.assertLessEqual(len(criteria), 24)
                self.assertLess(len(json.dumps({'state': state, 'questions': questions}).encode()), 60000)
                return super().evaluate(state, questions)
        agent = SimulationJEVAgent(Backend()); agent.rollouts = 120
        choice = agent.decide(ctx).action_id
        self.assertIn(choice, [a.id for a in ctx.observation.legal_actions])
        self.assertEqual(len(agent.last_selection), 1)
        self.assertIn('simulation', agent.last_features['candidate_consequences'][choice])

    def test_v3_more_options_keeps_every_action_reachable(self):
        game = FullDoudizhuGame()
        hand = ordered('3 3 3 4 4 4 5 5 5 6 6 6 7 8 9 10 J Q K A'.split())
        state = State((hand, ('2',), ('SJ',)), (), 0, phase='playing', landlord=0, bid_score=1)
        ctx = context(game, state)
        seen = set()
        class Backend(RecordingBackend):
            def evaluate(inner, state, questions):
                ids = questions['action']['criteria']
                result = super().evaluate(state, questions)
                pick = 'more_options' if 'more_options' in ids else list(ids)[-1]
                seen.update(ids)
                result['answers']['action'].update(choice=pick, probabilities={k: float(k == pick) for k in ids})
                return result
        agent = SimulationJEVAgent(Backend()); agent.rollouts = 60
        choice = agent.decide(ctx).action_id
        self.assertIn(choice, [a.id for a in ctx.observation.legal_actions])
        self.assertGreater(len(agent.last_selection), 1)

    def test_v3_episode_completes_with_recorded_simulation(self):
        from joker_jev.games.doudizhu.full.match import run_episode
        with tempfile.TemporaryDirectory() as directory:
            episode = run_episode(5, 'p1', Path(directory) / 'v3.json', RecordingBackend(), strategy='v3')
            self.assertEqual(episode['status'], 'completed')
            jev_rows = [r for r in episode['trace'] if r['player'] == 'p1' and 'strategy_features' in r]
            self.assertTrue(jev_rows)
            self.assertIn('simulation_config', jev_rows[0]['strategy_features'])


if __name__ == '__main__':
    unittest.main()
