from collections import Counter
import unittest

from joker_jev.games.doudizhu.heldout import make_mixed_cases, manifest, SCENARIO_KINDS
from joker_jev.games.doudizhu.strategy import DECK, player_state
from joker_jev.games.doudizhu.rollout import compatible_worlds
from joker_jev.games.doudizhu.episode import run_episode


class MixedCasesTests(unittest.TestCase):
    def test_deterministic_structural_coverage_and_physical_cards(self):
        cases = make_mixed_cases(123, 50)
        self.assertEqual(cases, make_mixed_cases(123, 50))
        self.assertEqual(Counter(c['scenario_kind'] for c in cases), {k: 10 for k in SCENARIO_KINDS})
        self.assertEqual({c['position'].passes for c in cases if c['position'].target}, {0, 1})
        self.assertEqual({c['position'].actor for c in cases}, {0, 1, 2})
        for c in cases:
            p = c['position']
            p.validate()
            self.assertGreater(len(set(map(len, p.hands))), 1)
            total = Counter(card for hand in p.hands for card in hand) + Counter(p.target)
            self.assertFalse(total - DECK)
            if c['scenario_kind'].startswith('landlord_'):
                self.assertEqual(len(p.hands[0]), 1 if c['scenario_kind'] == 'landlord_one' else 2)
            if c['scenario_kind'].startswith('respond_'):
                self.assertEqual(len(p.target), 1 if c['scenario_kind'] == 'respond_single' else 2)
            view = player_state(p)
            worlds = compatible_worlds(view)
            self.assertTrue(any(world == p for world, _ in worlds))
            self.assertAlmostEqual(sum(weight for _, weight in worlds), 1)
        self.assertEqual(manifest(cases, 123, 'doudizhu_mixed_v1')['generator'], 'doudizhu_mixed_v1')

    def test_mixed_snapshots_run_to_terminal(self):
        for case in make_mixed_cases(124, 10):
            result = run_episode(case['position'], 'simulation', 'farmer_before')
            self.assertEqual(result['status'], 'completed')
            self.assertIn(result['team_reward'], (-1, 1))
