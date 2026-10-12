from collections import Counter
from contextlib import redirect_stdout
from dataclasses import replace
from functools import lru_cache
import io
import json
from pathlib import Path
import tempfile
import unittest

from joker_jev.games.doudizhu.full.cards import ordered, all_moves, classify
from joker_jev.games.doudizhu.full.game import FullDoudizhuGame, State
from joker_jev.games.doudizhu.full.agents import StrategicJEVAgent
from joker_jev.games.doudizhu.full.strategy import HandPlanner, features
from joker_jev.games.doudizhu.full.compare_strategies import run_comparison, summary
from test_full_doudizhu import context, take
from test_fullgame import RecordingBackend


class FullStrategyTests(unittest.TestCase):
    def assert_valid_partition(self, hand, plan):
        self.assertEqual(Counter(hand), Counter(c for m in plan['feasible_partition'] for c in m['cards']))
        self.assertEqual(len(plan['feasible_partition']), plan['remaining_plays_upper_bound'])
        for m in plan['feasible_partition']:
            self.assertIn(m['kind'], [c.kind for c in classify(m['cards'])])

    def test_partitions_preserve_cards_and_budget_is_explicit(self):
        hand = ordered('3 3 3 4 4 4 5 5 5 6 6 6 7 8 9 10 J Q K A'.split())
        for budget in (0, 20, 4000):
            planner = HandPlanner(hand, node_budget=budget)
            self.assert_valid_partition(hand, planner.after(()))
            remaining = list(hand); remaining.remove('3')
            self.assert_valid_partition(remaining, planner.after(('3',)))
            self.assertLessEqual(planner.nodes, budget)
            if budget == 0:
                self.assertTrue(planner.truncated)

    def test_partition_small_hand_counts_match_unanchored_search(self):
        @lru_cache(None)
        def exhaustive(hand):
            if not hand:
                return 0
            counts = Counter(hand)
            return 1 + min(exhaustive(ordered((counts - Counter(m.cards)).elements())) for m in all_moves(hand))
        for text in ('3 3 3 4 4 4 5 5', '3 3 3 3 4 4 5 5', '3 4 5 6 7 8 9 SJ BJ'):
            hand = ordered(text.split()); planner = HandPlanner(hand)
            self.assertEqual(planner.after(())['remaining_plays_upper_bound'], exhaustive(hand))
            self.assertFalse(planner.truncated)

    def test_features_are_identical_under_hidden_reassignment(self):
        game = FullDoudizhuGame(); s = take(game, game.initial_state(0), 'bid:3').state
        other = replace(s, hands=(s.hands[0], s.hands[2], s.hands[1]), seed=123456)
        self.assertEqual(features(context(game, s)), features(context(game, other)))

    def test_pass_consequence_is_visible_but_not_forced(self):
        game = FullDoudizhuGame()
        target = classify(('J',))[0]
        s = State((('Q',), ('5', '6'), ('A', '2')), (), 2, phase='playing', landlord=0,
                  bid_score=1, target=target, owner=0, passes=1)
        ctx = context(game, s)
        common, choices = features(ctx)
        self.assertTrue(choices['pass']['passes_to_enemy_owner'])
        self.assertEqual(common['urgent_enemies'], ['p0'])
        class PassBackend(RecordingBackend):
            def evaluate(self, state, questions):
                response = super().evaluate(state, questions)
                ids = questions['action']['criteria']
                self.assertion.assertEqual(set(ids), {a.id for a in ctx.observation.legal_actions})
                response['answers']['action'].update(choice='pass', probabilities={k: float(k == 'pass') for k in ids})
                return response
        backend = PassBackend(); backend.assertion = self
        self.assertEqual(StrategicJEVAgent(backend).decide(ctx).action_id, 'pass')

    def test_compact_choice_has_bounded_payload_and_preserves_legal_selection(self):
        from joker_jev.games.doudizhu.full.agents import CompactStrategicJEVAgent
        game = FullDoudizhuGame()
        hand = ordered('3 3 3 4 4 4 5 5 5 6 6 6 7 8 9 10 J Q K A'.split())
        state = State((hand, ('2',), ('SJ',)), (), 0, phase='playing', landlord=0, bid_score=1)
        ctx = context(game, state)
        class Backend(RecordingBackend):
            def evaluate(inner, state, questions):
                self.assertLess(len(json.dumps({'state': state, 'questions': questions}).encode()), 60000)
                ids = questions['action']['criteria']
                if all('label' in value for value in ids.values()):
                    self.assertLessEqual(len(ids), 24)
                result = super().evaluate(state, questions)
                if 'airplane_single' in ids:
                    result['answers']['action'].update(choice='airplane_single', probabilities={k: float(k == 'airplane_single') for k in ids})
                return result
        choice = CompactStrategicJEVAgent(Backend()).decide(ctx)
        self.assertIn(choice.action_id, [a.id for a in ctx.observation.legal_actions])

    def test_fresh_set_covers_all_relative_bidding_positions(self):
        from joker_jev.games.doudizhu.full.compare_strategies import make_settings
        settings = make_settings(10)
        positions = Counter((int(s['focal'][1:]) - int(s['first_bidder'][1:])) % 3
                            for s in settings if s['split'] == 'fresh')
        self.assertEqual(sorted(positions.values()), [3, 3, 4])
        self.assertEqual([s['seed'] for s in settings if s['split'] == 'fresh'], list(range(20261201, 20261211)))

    def test_invalid_choice_retains_response_and_separates_protocol_errors(self):
        from joker_jev.games.doudizhu.full.match import run_episode, summarize
        class InvalidBackend(RecordingBackend):
            def evaluate(self, state, questions):
                result = super().evaluate(state, questions)
                result['answers']['action']['choice'] = 'not-offered'
                return result
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'invalid.json'
            episode = run_episode(11, 'p0', path, InvalidBackend(), strategy='v2_compact')
            self.assertEqual(episode['status'], 'api_error')
            self.assertEqual(episode['error_kind'], 'response_validation')
            self.assertIsNone(episode['team_reward'])
            saved = json.loads(path.read_text())
            self.assertEqual(saved['trace'][-1]['selection'][-1]['status'], 'invalid_response')
            counts = summarize([episode])
            self.assertEqual(counts['api_errors'], 0)
            self.assertEqual(counts['api_error_episodes'], 1)
            self.assertEqual(counts['response_validation_errors'], 1)

    def test_comparison_freezes_both_splits_and_pairs_versions(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            path = Path(directory) / 'compare.json'
            def factory():
                frozen = json.loads(path.read_text())
                self.assertEqual({s['split'] for s in frozen['settings']}, {'development', 'fresh'})
                return RecordingBackend()
            result = run_comparison(path, factory, count=1, workers=2)
            self.assertEqual(len(result['episodes']), 4)
            for split in ('development', 'fresh'):
                self.assertEqual(result['summary'][split]['paired_settings'], 1)
            self.assertTrue(path.with_suffix('.md').exists())
            incomplete = [dict(e) for e in result['episodes']]
            incomplete[0].update(status='api_error', team_reward=None)
            self.assertEqual(summary(incomplete)[incomplete[0]['split']]['paired_settings'], 0)
