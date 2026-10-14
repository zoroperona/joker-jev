import unittest
from server import Table


class TableTests(unittest.TestCase):
    def test_complete_games_and_private_view(self):
        for seed in range(12):
            table = Table(seed=seed)
            before = table.snapshot()
            self.assertEqual(before['public']['bottom_cards'], [])
            self.assertEqual(set(before['private']), {'hand', 'role', 'teammate'})
            for _ in range(400):
                if table.state.phase == 'finished':
                    break
                table.act(table.choice())
            self.assertEqual(table.state.phase, 'finished')
            self.assertEqual(sum(table.rewards.values()), 0)
            self.assertTrue(any(table.rewards.values()))
            self.assertEqual(table.totals, table.rewards)

    def test_validation_hint_and_stale_action(self):
        table = Table(seed=42)
        rev = table.revision
        hint = table.command({'command': 'hint', 'revision': rev})
        self.assertEqual(table.revision, rev)
        with self.assertRaises(ValueError):
            table.command({'command': 'action', 'revision': rev - 1, **hint})
        with self.assertRaises(ValueError):
            table.command({'command': 'action', 'revision': rev, 'action_id': 'pass'})
        table.command({'command': 'action', 'revision': rev, **hint})
        self.assertGreater(table.revision, rev)
        for invalid in (True, None, 'fast', 0, 6, float('nan')):
            with self.assertRaises(ValueError):
                table.command({'command': 'speed', 'delay': invalid})

    def test_autoplay_and_takeover(self):
        table = Table(seed=42)
        original = table.revision
        table.due = 0
        table.tick()
        self.assertEqual(table.revision, original)
        table.command({'command': 'mode', 'auto': True})
        for _ in range(400):
            table.due = 0
            table.tick()
            if table.round == 2:
                break
        self.assertEqual(table.round, 2)
        table.command({'command': 'mode', 'auto': False})
        for _ in range(20):
            table.due = 0
            table.tick()
            if table.state.actor == 0:
                break
        rev = table.revision
        table.due = 0
        table.tick()
        self.assertEqual(table.revision, rev)


class AIControlTests(unittest.TestCase):
    def test_slow_decision_is_nonblocking_and_discarded_after_stop(self):
        import threading
        from joker_jev.core.models import Decision
        entered, release = threading.Event(), threading.Event()
        class SlowAgent:
            def decide(self, ctx):
                entered.set()
                release.wait(5)
                return Decision(ctx.observation.legal_actions[0].id)
        table = Table(auto=True, seed=42, opponent=SlowAgent())
        table.due = 0
        worker = threading.Thread(target=table.tick)
        worker.start()
        self.assertTrue(entered.wait(2))
        self.assertTrue(table.snapshot()['thinking'])
        table.command({'command': 'mode', 'auto': False})
        release.set()
        worker.join(2)
        self.assertEqual(table.history, ())
        self.assertFalse(table.thinking)

    def test_failures_pause_without_fallback_and_retry_is_explicit(self):
        class BrokenAgent:
            def decide(self, ctx):
                raise RuntimeError('test failure')
        table = Table(auto=True, seed=42, opponent=BrokenAgent())
        table.due = 0
        table.tick()
        self.assertIsNotNone(table.error)
        self.assertFalse(table.auto)
        self.assertFalse(table.thinking)
        self.assertEqual(table.history, ())
        table.command({'command': 'retry'})
        self.assertIsNone(table.error)

    def test_configuration_restarts_and_needs_jev_backend(self):
        table = Table(seed=42)
        with self.assertRaises(ValueError):
            table.command({'command': 'configure', 'controller': 'jev', 'jev_mode': 'minimal'})
        before = table.round
        table.command({'command': 'configure', 'controller': 'douzero', 'jev_mode': 'assisted'})
        self.assertEqual(table.round, before + 1)
        self.assertTrue(table.auto)
        self.assertEqual(table.jev_mode, 'assisted')


    def test_jev_mode_selects_matching_input_agent(self):
        class Backend:
            def __init__(self):
                self.states = []
            def evaluate(self, state, questions):
                self.states.append(state)
                criteria = questions['action']['criteria']
                choice = next(iter(criteria))
                return {'answers': {'action': {'type': 'choice', 'choice': choice, 'confidence': 1,
                        'probabilities': {k: float(k == choice) for k in criteria}}}}
        for mode in ('minimal', 'assisted'):
            backend = Backend()
            table = Table(auto=True, seed=42, backend=backend, controller='jev', jev_mode=mode)
            table.due = 0
            table.tick()
            self.assertIsNone(table.error)
            self.assertTrue(table.history)
            self.assertEqual('decision_facts' in backend.states[0], mode == 'assisted')


if __name__ == '__main__':
    unittest.main()
