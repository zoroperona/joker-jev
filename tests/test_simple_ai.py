from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest

from joker_jev.agents.typesafe import TypeSafeError
from joker_jev.core.engine import play
from joker_jev.games.doudizhu.environment import EndgameGame
from joker_jev.games.doudizhu.heldout import make_mixed_cases
from joker_jev.games.doudizhu.match import run_match
from joker_jev.games.doudizhu.scenarios import position
from joker_jev.games.doudizhu.simple_ai import SimpleDoudizhuAgent, choose_simple
from joker_jev.games.doudizhu.strategy import SEATS, player_state
from test_fullgame import RecordingBackend


class SimpleAITests(unittest.TestCase):
    def test_legal_deterministic_and_no_view_mutation(self):
        for case in make_mixed_cases(321, 50):
            view = player_state(case['position'])
            before = deepcopy(view)
            first = choose_simple(view)
            self.assertIn(first, [a['id'] for a in view['legal_actions']])
            self.assertEqual(first, choose_simple(view))
            self.assertEqual(view, before)

    def test_finish_yield_guard_and_pair_control(self):
        self.assertEqual(choose_simple(player_state(position(('3', '4 5', '6 7'), 0))), 'play:3')
        yield_view = player_state(position(('4 5', '6 7', '8 9'), 1).advance(('6',)))
        self.assertEqual(choose_simple(yield_view), 'pass')
        guard_view = player_state(position(('Q', '3 K 2', '4 5'), 1, 'J', 0))
        self.assertEqual(choose_simple(guard_view), 'play:2')
        pair_view = player_state(position(('Q', '3 3 K', '4 5'), 1))
        self.assertEqual(choose_simple(pair_view), 'play:3,3')

    def test_agent_uses_shared_engine(self):
        for case in make_mixed_cases(322, 10):
            result = play(EndgameGame(case['position']), {p: SimpleDoudizhuAgent() for p in SEATS}, max_turns=36)
            self.assertEqual(result.rewards['farmer_after'], result.rewards['farmer_before'])
            self.assertEqual(result.rewards['landlord'], -result.rewards['farmer_after'])

    def test_ten_game_protocol_freezes_settings_before_api_and_writes_results(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            path = Path(directory) / 'match.json'
            def factory():
                frozen = json.loads(path.read_text())
                self.assertEqual(len(frozen['settings']), 10)
                self.assertEqual(len(frozen['manifest']['cases']), 10)
                return RecordingBackend()
            result = run_match(path, factory, seed=323)
            self.assertEqual(result['metrics']['attempted'], 10)
            self.assertEqual(result['metrics']['completed'], 10)
            self.assertEqual(result['metrics']['team_wins'] + result['metrics']['team_losses'], 10)
            self.assertEqual([result['by_seat'][p]['attempted'] for p in SEATS], [4, 3, 3])
            self.assertTrue(path.with_suffix('.md').exists())
            for e in result['episodes']:
                self.assertTrue((path.parent / e['trace_path']).exists())
                for seat, policy in e['policy_by_seat'].items():
                    self.assertEqual(policy, 'current_jev' if seat == e['focal_seat'] else 'simple')
            with self.assertRaises(ValueError):
                run_match(path, factory)

    def test_api_errors_remain_in_ten_attempts_and_not_losses(self):
        class Failing:
            def evaluate(self, state, questions):
                raise TypeSafeError('test unavailable')
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            result = run_match(Path(directory) / 'failed.json', Failing, seed=323)
            self.assertEqual(result['metrics']['attempted'], 10)
            self.assertGreater(result['metrics']['api_errors'], 0)
            for episode in result['episodes']:
                if episode['status'] == 'api_error':
                    self.assertIsNone(episode['team_reward'])
            self.assertEqual(result['metrics']['team_losses'] + result['metrics']['team_wins'], result['metrics']['completed'])
