from collections import Counter
from dataclasses import replace
from itertools import product
import random
import unittest

from joker_jev.agents.base import RandomAgent
from joker_jev.core.engine import play
from joker_jev.core.models import DecisionContext, Observation
from joker_jev.games import create_game
from joker_jev.games.doudizhu.full.cards import DECK, RANKS, ordered, all_moves, classify, beats
from joker_jev.games.doudizhu.full.game import FullDoudizhuGame, PLAYERS, State
from joker_jev.games.doudizhu.full.agents import FullSimpleAgent, FullJEVAgent
from test_fullgame import RecordingBackend


def context(game, state):
    player = game.current_player(state)
    view = game.view(state, player)
    obs = Observation('doudizhu', player, 0, view.private, view.public, game.legal_actions(state), ())
    return DecisionContext(game.rules, obs, game.create_inference().infer(obs), 0)


def take(game, state, action_id):
    return game.step(state, next(a for a in game.legal_actions(state) if a.id == action_id))


def reference(cards):
    """独立的子集分类判据，用于验证生成器的完整性。"""
    c = Counter(cards)
    ranks = sorted(RANKS.index(r) for r in c)
    n = len(cards)
    out = set()
    def add(kind, main, chain=1):
        out.add((ordered(cards), kind, main, chain))
    if n in (1, 2, 3, 4) and len(c) == 1:
        add({1: 'single', 2: 'pair', 3: 'triple', 4: 'bomb'}[n], ranks[0])
    if c == Counter(('SJ', 'BJ')):
        add('rocket', 14)
    if sorted(c.values()) == [1, 3]:
        add('triple_single', RANKS.index(next(r for r in c if c[r] == 3)))
    if sorted(c.values()) == [2, 3]:
        add('triple_pair', RANKS.index(next(r for r in c if c[r] == 3)))
    if len(ranks) >= 2 and ranks[-1] < 12 and ranks == list(range(ranks[0], ranks[-1] + 1)):
        if set(c.values()) == {1} and n >= 5:
            add('straight', ranks[-1], len(ranks))
        if set(c.values()) == {2} and n >= 6:
            add('pair_straight', ranks[-1], len(ranks))
        if set(c.values()) == {3}:
            add('airplane', ranks[-1], len(ranks))
    for rank in c:
        if c[rank] == 4:
            rest = c.copy(); del rest[rank]
            if n == 6 and max(rest.values()) <= 2 and not (rest['SJ'] and rest['BJ']):
                add('four_two_single', RANKS.index(rank))
            if n == 8 and sorted(rest.values()) == [2, 2]:
                add('four_two_pair', RANKS.index(rank))
    for kind, divisor in (('airplane_single', 4), ('airplane_pair', 5)):
        if n % divisor or n // divisor < 2:
            continue
        k = n // divisor
        for start in range(13 - k):
            body = RANKS[start:start + k]
            if not all(c[r] == 3 for r in body):
                continue
            rest = Counter({r: v for r, v in c.items() if r not in body})
            if kind == 'airplane_single' and sum(rest.values()) == k and max(rest.values()) <= 2 and not (rest['SJ'] and rest['BJ']):
                add(kind, start + k - 1, k)
            if kind == 'airplane_pair' and len(rest) == k and set(rest.values()) == {2}:
                add(kind, start + k - 1, k)
    return out


class FullCardsTests(unittest.TestCase):
    def test_every_supported_type(self):
        examples = {'single': '2', 'pair': 'A A', 'triple': '2 2 2',
                    'triple_single': '3 3 3 BJ', 'triple_pair': '4 4 4 2 2',
                    'straight': '10 J Q K A', 'pair_straight': 'Q Q K K A A',
                    'airplane': '3 3 3 4 4 4', 'airplane_single': '3 3 3 4 4 4 5 5',
                    'airplane_pair': '3 3 3 4 4 4 5 5 6 6',
                    'four_two_single': '3 3 3 3 4 4', 'four_two_pair': '3 3 3 3 4 4 5 5',
                    'bomb': '2 2 2 2', 'rocket': 'SJ BJ'}
        for kind, cards in examples.items():
            self.assertIn(kind, [m.kind for m in classify(cards.split())])
        for invalid in ('J Q K A 2', '3 3 4 4', '3 3 3 4 4 4 SJ BJ', '3 3 3 3 4 4 4 5', '3 3 3 3 SJ BJ'):
            self.assertFalse(classify(invalid.split()), invalid)

    def test_size_type_and_bomb_comparison(self):
        get = lambda s: classify(s.split())[0]
        self.assertTrue(beats(get('4 5 6 7 8'), get('3 4 5 6 7')))
        self.assertFalse(beats(get('4 5 6 7 8 9'), get('3 4 5 6 7')))
        self.assertFalse(beats(get('2 2'), get('A')))
        self.assertTrue(beats(get('3 3 3 3'), get('2')))
        self.assertTrue(beats(get('SJ BJ'), get('2 2 2 2')))
        self.assertFalse(beats(get('2 2 2 2'), get('SJ BJ')))
        self.assertFalse(beats(get('SJ BJ'), get('SJ BJ')))

    def test_generator_equals_independent_exhaustive_subsets(self):
        for text in ('3 3 3 3 4 4 4 5 5 5 6 6', '3 3 3 4 4 4 5 5 6 6 SJ BJ', '3 4 5 6 7 8 9 10 J Q K A'):
            hand = ordered(text.split())
            counts = Counter(hand)
            ranks = list(counts)
            expected = set()
            for nums in product(*(range(counts[r] + 1) for r in ranks)):
                cards = tuple(r for r, n in zip(ranks, nums) for _ in range(n))
                if cards:
                    expected.update(reference(cards))
            actual = {(m.cards, m.kind, m.main, m.chain) for m in all_moves(hand)}
            self.assertEqual(actual, expected)


class FullGameTests(unittest.TestCase):
    def test_deal_privacy_bidding_and_redeal(self):
        g = FullDoudizhuGame(); s = g.initial_state(0)
        self.assertEqual([len(h) for h in s.hands], [17, 17, 17])
        self.assertEqual(Counter(c for h in s.hands for c in h) + Counter(s.bottom), Counter(DECK))
        self.assertEqual(g.view(s, 'p0').public['bottom_cards'], [])
        self.assertNotIn('seed', g.view(s, 'p0').public)
        original = s
        for _ in range(3):
            s = take(g, s, 'bid:0').state
        self.assertEqual(s.deal_number, 1)
        self.assertNotEqual(s.hands, original.hands)
        self.assertEqual(s, g._deal(0, 1))
        # 首家叫 1 分、后两家过，原叫分者成为地主。
        first = s.actor
        s = take(g, s, 'bid:1').state
        self.assertIsNone(s.landlord)
        self.assertEqual(g.view(s, PLAYERS[s.actor]).public['bottom_cards'], [])
        self.assertEqual([a.id for a in g.legal_actions(s)], ['bid:0', 'bid:2', 'bid:3'])
        s = take(g, s, 'bid:0').state
        s = take(g, s, 'bid:0').state
        self.assertEqual(s.landlord, first)
        self.assertEqual(s.actor, first)
        self.assertEqual(len(s.hands[first]), 20)
        self.assertEqual(s.bid_score, 1)
        self.assertEqual(tuple(g.view(s, 'p0').public['bottom_cards']), s.bottom)
        self.assertNotIn('pass', [a.id for a in g.legal_actions(s)])

    def test_three_bid_immediate_and_higher_bid_replaces(self):
        g = FullDoudizhuGame(); s = g.initial_state(0)
        s = take(g, s, 'bid:1').state
        s = take(g, s, 'bid:2').state
        s = take(g, s, 'bid:0').state
        self.assertEqual((s.landlord, s.bid_score), (1, 2))
        s = take(g, g.initial_state(0), 'bid:3').state
        self.assertEqual((s.phase, s.landlord, s.actor), ('playing', 0, 0))

    def test_pass_reset_and_scoring_spring_bomb(self):
        g = FullDoudizhuGame()
        s = State((ordered('3 3 3 3 4'.split()), ('5',), ('6',)), (), 0,
                  phase='playing', landlord=0, bid_score=2)
        bomb = next(a for a in g.legal_actions(s) if a.payload['kind'] == 'bomb')
        s = g.step(s, bomb).state
        self.assertEqual(s.bombs, 1)
        s = take(g, s, 'pass').state
        s = take(g, s, 'pass').state
        self.assertEqual((s.actor, s.target, s.passes), (0, None, 0))
        end = g.step(s, g.legal_actions(s)[0])
        self.assertTrue(end.state.spring)
        self.assertEqual(end.rewards, {'p0': 16, 'p1': -8, 'p2': -8})
        self.assertEqual(g.legal_actions(end.state), ())

    def test_reverse_spring_and_rocket(self):
        g = FullDoudizhuGame()
        s = State((('3', '4'), ('SJ', 'BJ'), ('6',)), (), 1, phase='playing',
                  landlord=0, bid_score=3, play_counts=(1, 0, 0))
        action = next(a for a in g.legal_actions(s) if a.payload['kind'] == 'rocket')
        t = g.step(s, action)
        self.assertTrue(t.state.spring)
        self.assertEqual(t.rewards, {'p0': -24, 'p1': 12, 'p2': 12})

    def test_full_games_conservation_and_zero_sum(self):
        g = create_game('doudizhu')
        for seed in range(12):
            agents = {p: FullSimpleAgent() if seed % 2 else RandomAgent(seed * 3 + i) for i, p in enumerate(PLAYERS)}
            s = g.initial_state(seed)
            for turn in range(250):
                decision = agents[g.current_player(s)].decide(context(g, s))
                t = take(g, s, decision.action_id)
                s = t.state
                total = Counter(c for h in s.hands for c in h) + Counter(c for h in s.played for c in h)
                if s.phase == 'bidding':
                    total.update(s.bottom)
                self.assertEqual(total, Counter(DECK))
                self.assertEqual(sum(t.rewards.values()), 0)
                if g.is_terminal(s):
                    self.assertEqual(sum(not h for h in s.hands), 1)
                    self.assertNotEqual(t.rewards['p0'], 0)
                    break
            else:
                self.fail('未到自然终局')

    def test_inference_expected_counts_and_public_bottom_constraints(self):
        g = FullDoudizhuGame(); s = take(g, g.initial_state(1), 'bid:3').state
        # 切换到农民视角，同时保持发牌状态。
        s = replace(s, actor=(s.landlord + 1) % 3)
        ctx = context(g, s)
        b = ctx.belief
        self.assertEqual(b.facts['known_landlord_minimum'], dict(Counter(s.bottom)))
        for p, counts in b.estimates['expected_rank_counts'].items():
            self.assertAlmostEqual(sum(counts.values()), len(s.hands[PLAYERS.index(p)]))
        self.assertNotIn('hands', ctx.observation.public)

    def test_hidden_hand_reassignment_cannot_change_player_view_or_actions(self):
        g = FullDoudizhuGame()
        s = take(g, g.initial_state(0), 'bid:3').state
        hidden_swapped = replace(s, hands=(s.hands[0], s.hands[2], s.hands[1]), seed=999999)
        a, b = context(g, s), context(g, hidden_swapped)
        self.assertEqual(a, b)
        self.assertEqual(FullSimpleAgent().decide(a), FullSimpleAgent().decide(b))

    def test_non_spring_farmer_reward(self):
        g = FullDoudizhuGame()
        s = State((('3', '4'), ('A',), ('6',)), (), 1, phase='playing',
                  landlord=0, bid_score=2, play_counts=(2, 1, 1))
        t = g.step(s, g.legal_actions(s)[0])
        self.assertFalse(t.state.spring)
        self.assertEqual(t.rewards, {'p0': -4, 'p1': 2, 'p2': 2})

    def test_jev_hierarchical_selection_without_pruning(self):
        g = FullDoudizhuGame()
        hand = ordered('3 3 3 4 4 4 5 5 5 6 6 6 7 8 9 10 J Q K A'.split())
        s = State((hand, ('2',), ('SJ',)), (), 0, phase='playing', landlord=0, bid_score=1)
        ctx = context(g, s)
        self.assertGreater(len(ctx.observation.legal_actions), 255)
        class Backend(RecordingBackend):
            def evaluate(self, state, questions):
                self.test.assertLessEqual(len(questions['action']['criteria']), 255)
                self.test.assertNotIn('hands', state)
                self.test.assertNotIn('legal_actions', state)
                response = super().evaluate(state, questions)
                ids = questions['action']['criteria']
                if 'airplane_single' in ids:
                    response['answers']['action']['choice'] = 'airplane_single'
                    response['answers']['action']['probabilities'] = {k: float(k == 'airplane_single') for k in ids}
                return response
        backend = Backend(); backend.test = self
        agent = FullJEVAgent(backend)
        decision = agent.decide(ctx)
        self.assertIn(decision.action_id, [a.id for a in ctx.observation.legal_actions])
        self.assertEqual(len(backend.requests), 3)
        # 每个固定主体的附件全部可以作为最终 Choice 候选。
        bodies = Counter((a.payload['kind'], a.payload['main'], a.payload['chain']) for a in ctx.observation.legal_actions)
        self.assertLessEqual(max(bodies.values()), 255)


class FullMatchTests(unittest.TestCase):
    def test_live_protocol_freeze_and_failure_retention(self):
        import json
        from pathlib import Path
        import tempfile
        from joker_jev.agents.typesafe import TypeSafeError
        from joker_jev.games.doudizhu.full.match import run_suite
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'live.json'
            def factory():
                frozen = json.loads(path.read_text())
                self.assertEqual(len(frozen['manifest']['settings']), 1)
                self.assertEqual(len(frozen['manifest']['initial_deals'][0]['bottom']), 3)
                return RecordingBackend()
            report = run_suite(path, count=1, seed=11, backend_factory=factory)
            self.assertEqual(report['summary']['completed'], 1)
            self.assertEqual(report['summary']['api_errors'], 0)
            self.assertTrue(path.with_suffix('.md').exists())
            with self.assertRaises(ValueError):
                run_suite(path, count=1)
            class Failing:
                def evaluate(self, state, questions):
                    raise TypeSafeError('test outage')
            failed = run_suite(Path(directory) / 'failed.json', count=1, seed=11, backend_factory=Failing)
            self.assertEqual(failed['summary']['status_counts'], {'api_error': 1})
            self.assertEqual(failed['summary']['team_losses'], 0)
            self.assertIsNone(failed['episodes'][0]['team_reward'])

    def test_turn_limit_is_not_a_game_loss(self):
        from pathlib import Path
        import tempfile
        from joker_jev.games.doudizhu.full.match import run_episode
        with tempfile.TemporaryDirectory() as directory:
            result = run_episode(12, 'p0', Path(directory) / 'cap.json', max_turns=1)
            self.assertEqual(result['status'], 'turn_limit')
            self.assertIsNone(result['rewards'])
