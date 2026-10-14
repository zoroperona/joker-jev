from collections import Counter
from copy import deepcopy
from dataclasses import replace
import unittest

from joker_jev.core.models import DecisionContext, Observation
from joker_jev.games.doudizhu.full.cards import DECK
from joker_jev.games.doudizhu.full.game import FullDoudizhuGame
from joker_jev.games.doudizhu.full.douzero import infoset, encode, POSITIONS
from joker_jev.games.doudizhu.full.input_modes import InputModeJEVAgent
from joker_jev.games.doudizhu.full.agents import FullSimpleAgent


def context(game, state, history=()):
    player = game.current_player(state)
    view = game.view(state, player)
    obs = Observation('doudizhu', player, len(history), view.private, view.public,
                      game.legal_actions(state), history)
    return DecisionContext(game.rules, obs, game.create_inference().infer(obs), 0)


class RecordingBackend:
    def __init__(self):
        self.calls = []

    def evaluate(self, state, questions):
        self.calls.append(deepcopy((state, questions)))
        criteria = questions['action']['criteria']
        choice = next(iter(criteria))
        return {'answers': {'action': {'type': 'choice', 'choice': choice, 'confidence': 1,
                                       'probabilities': {k: float(k == choice) for k in criteria}}}}


class InputTests(unittest.TestCase):
    def test_modes_change_information_not_legal_options_or_instructions(self):
        game = FullDoudizhuGame()
        state = game.initial_state(42)
        transition = game.step(state, next(a for a in game.legal_actions(state) if a.id == 'bid:3'))
        ctx = context(game, transition.state, transition.events)
        backends = [RecordingBackend(), RecordingBackend()]
        decisions = [InputModeJEVAgent(b, m).decide(ctx) for b, m in zip(backends, ('minimal', 'assisted'))]
        self.assertEqual(decisions[0].action_id, decisions[1].action_id)
        minimal, assisted = [b.calls[-1] for b in backends]
        self.assertNotIn('belief', minimal[0])
        self.assertNotIn('decision_facts', minimal[0])
        self.assertIn('belief', assisted[0])
        self.assertIn('decision_facts', assisted[0])
        self.assertEqual(minimal[0]['history'], assisted[0]['history'])
        self.assertEqual(minimal[1]['action']['instructions'], assisted[1]['action']['instructions'])
        self.assertEqual(list(minimal[1]['action']['criteria']), list(assisted[1]['action']['criteria']))
        self.assertTrue(all('consequences' not in v for v in minimal[1]['action']['criteria'].values()))
        self.assertTrue(all('consequences' in v for v in assisted[1]['action']['criteria'].values()))

    def test_choice_groups_are_bounded_and_last_option_stays_reachable(self):
        class LastBackend(RecordingBackend):
            def evaluate(inner, state, questions):
                criteria = questions['action']['criteria']
                self.assertLessEqual(len(criteria), 24)
                result = super().evaluate(state, questions)
                last = list(criteria)[-1]
                result['answers']['action'].update(choice=last,
                    probabilities={k: float(k == last) for k in criteria})
                return result
        backend = LastBackend()
        agent = InputModeJEVAgent(backend)
        selected = agent._choose({}, {str(i): {'label': str(i)} for i in range(700)}, 'choose')
        self.assertEqual(selected, '699')

    def test_relative_positions_and_no_hidden_allocation(self):
        game = FullDoudizhuGame()
        for seed in range(3):
            state = game.initial_state(seed)
            transition = game.step(state, next(a for a in game.legal_actions(state) if a.id == 'bid:3'))
            state = transition.state
            landlord = state.landlord
            for offset, role in enumerate(POSITIONS):
                actor = (landlord + offset) % 3
                view_state = replace(state, actor=actor)
                ctx = context(game, view_state, transition.events)
                visible = infoset(ctx)
                self.assertEqual(visible.player_position, role)
                other = [i for i in range(3) if i != actor]
                # Exchange a single unknown card, preserving public hand sizes.
                hands = [list(h) for h in view_state.hands]
                hands[other[0]][0], hands[other[1]][0] = hands[other[1]][0], hands[other[0]][0]
                changed = replace(view_state, hands=tuple(tuple(h) for h in hands))
                self.assertEqual(vars(visible), vars(infoset(context(game, changed, transition.events))))
                self.assertFalse(hasattr(visible, 'all_handcards'))
                self.assertEqual(Counter(visible.other_hand_cards), Counter(encode(DECK)) - Counter(encode(ctx.observation.private['hand'])))

    def test_play_history_counts_and_free_lead(self):
        game, agent = FullDoudizhuGame(), FullSimpleAgent()
        state, history = game.initial_state(9), ()
        saw_free = False
        for _ in range(300):
            if game.is_terminal(state):
                break
            ctx = context(game, state, history)
            if state.phase == 'playing':
                info = infoset(ctx)
                self.assertEqual(len(info.card_play_action_seq), sum(e.kind == 'move' for e in history))
                self.assertEqual(sum(info.num_cards_left_dict.values()) + sum(map(len, info.played_cards.values())), 54)
                if state.target is None and info.card_play_action_seq:
                    saw_free = True
                    self.assertEqual(info.last_move, [])
                    self.assertEqual(info.card_play_action_seq[-2:], [[], []])
            action = agent.decide(ctx).action_id
            result = game.step(state, next(a for a in ctx.observation.legal_actions if a.id == action))
            state, history = result.state, history + result.events
        self.assertTrue(saw_free)
        self.assertTrue(game.is_terminal(state))


if __name__ == '__main__':
    unittest.main()
