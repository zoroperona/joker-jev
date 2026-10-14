import copy
from collections import Counter
import unittest

from joker_jev.external.state import Play, PublicState, SEATS, DECK
from joker_jev.external.ui import UIMapper
from joker_jev.external.__main__ import ingest
from joker_jev.games.doudizhu.full.game import FullDoudizhuGame
from joker_jev.games.doudizhu.full.agents import FullSimpleAgent
from joker_jev.core.models import Observation, DecisionContext


class ExternalTests(unittest.TestCase):
    def test_public_tracker_matches_complete_games_without_opponent_hands(self):
        # Engine is an oracle only in this test; runtime tracker never receives it.
        for seed in range(6):
            game = FullDoudizhuGame()
            state = game.initial_state(seed)
            history = ()
            tracker = None
            for _ in range(400):
                player = game.current_player(state)
                view = game.view(state, player)
                obs = Observation('doudizhu', player, len(history), view.private, view.public,
                                  game.legal_actions(state), history)
                context = DecisionContext(game.rules, obs, game.create_inference().infer(obs), 0)
                if state.phase == 'playing' and tracker is None:
                    own = game.view(state, 'p0')
                    tracker = PublicState(own.private['hand'], SEATS[state.landlord])
                if tracker and player == 'p0':
                    expected = {tuple(a.payload['cards']) for a in obs.legal_actions}
                    self.assertEqual(set(tracker.actions()), expected)
                    self.assertEqual(Counter(tracker.hand), Counter(view.private['hand']))
                    info = tracker.infoset()
                    self.assertEqual(len(info.other_hand_cards), sum(tracker.remaining[s] for s in ('left','right')))
                decision = FullSimpleAgent().decide(context)
                action = next(a for a in obs.legal_actions if a.id == decision.action_id)
                result = game.step(state, action)
                state = result.state
                history += result.events
                for event in result.events:
                    if event.kind == 'move':
                        seat = SEATS[int(event.data['player'][1:])]
                        cards = tuple(event.data['cards'])
                        tracker.apply(Play(len(tracker.history)+1, seat, cards, tracker.remaining[seat]-len(cards)))
                        self.assertEqual(tracker.remaining, {SEATS[i]: len(h) for i,h in enumerate(state.hands)})
                if game.is_terminal(state):
                    self.assertTrue(tracker.finished)
                    break
            else:
                self.fail('Game did not terminate')

    def test_duplicates_gaps_and_atomic_validation(self):
        state = PublicState(DECK[:20], 'self')
        event = Play(1, 'self', ('3',), 19)
        self.assertTrue(state.apply(event))
        self.assertFalse(state.apply(event))
        before = copy.deepcopy(state.__dict__)
        for bad in [Play(1,'self',('4',),19), Play(3,'right',(),17),
                    Play(2,'left',(),17), Play(2,'right',('3','3','3','3'),13),
                    Play(2,'right',('4',),15)]:
            with self.assertRaises(ValueError):
                state.apply(bad)
            self.assertEqual(state.__dict__, before)

    def test_pass_cycle_resets_target(self):
        state = PublicState(DECK[:20], 'self')
        state.apply(Play(1,'self',('3',),19))
        state.apply(Play(2,'right',(),17))
        state.apply(Play(3,'left',(),17))
        self.assertIsNone(state.target)
        self.assertNotIn((), state.actions())

    def test_visible_history_must_be_contiguous(self):
        state = PublicState(DECK[:20], 'self')
        last = ingest(state, [(3,'你 3'), (4,'东篱 · 不出')], 2)
        self.assertEqual(last,4)
        with self.assertRaises(ValueError):
            ingest(state, [(6,'西窗 · 不出')], last)

    def test_ui_preserves_card_occurrences_and_fixed_button(self):
        targets = [{'id':str(i), 'rank':rank, 'x':i, 'y':0} for i,rank in enumerate(['3','3','4'])]
        buttons = [{'label':'出牌','x':10,'y':10}]
        plan = UIMapper().plan(('3','3'), targets, buttons)
        self.assertEqual([t['id'] for t in plan[:-1]],['0','1'])
        with self.assertRaises(ValueError):
            UIMapper().plan(('3','3','3'),targets,buttons)
        class WrongBackend:
            def evaluate(self, state, questions):
                return {'answers':{key: {'type':'choice','choice':'2','confidence':1}
                                   for key in questions}}
        with self.assertRaises(ValueError):
            UIMapper(WrongBackend()).plan(('3',),targets,buttons)


    def test_jev_maps_repeated_cards_as_groups(self):
        class Backend:
            def evaluate(self, state, questions):
                assert set(questions) == {'rank_3', 'rank_4', 'button'}
                assert [t['id'] for t in questions['rank_3']['criteria']['3']['elements']] == ['0','1']
                return {'answers':{key: {'type':'choice', 'choice':key[5:] if key.startswith('rank_') else '0',
                                         'confidence':1.0} for key in questions}}
        targets = [{'id':str(i), 'rank':rank, 'x':i, 'y':0} for i,rank in enumerate(['3','3','4','4'])]
        plan = UIMapper(Backend()).plan(('3','3','4','4'), targets, [{'label':'出牌','x':10,'y':10}])
        self.assertEqual(len({t['id'] for t in plan[:-1]}),4)


if __name__ == '__main__':
    unittest.main()
