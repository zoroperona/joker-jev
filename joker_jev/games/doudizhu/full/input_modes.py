"""Matched JEV selectors: only the supplied information changes between modes."""
from dataclasses import asdict
from copy import deepcopy

from joker_jev.core.models import Decision
from .agents import FullJEVAgent

MODES = ('minimal', 'assisted')
CHOICE_LIMIT = 24
INSTRUCTION = (
    'Choose the legal action maximizing your expected final score under the supplied rules. '
    'Use only your visible information. Other players\' hands are unknown. '
    'If auxiliary estimates are present, they are uncertain and do not constrain your choice.'
)


class InputModeJEVAgent(FullJEVAgent):
    def __init__(self, backend, mode='minimal'):
        super().__init__(backend)
        if mode not in MODES:
            raise ValueError('未知 JEV 信息模式')
        self.mode = mode
        self.last_features = None
        self.last_requests = []

    def _choose(self, state, criteria, instruction):
        if len(criteria) > CHOICE_LIMIT:
            items = list(criteria.items())
            width = (len(items) + CHOICE_LIMIT - 1) // CHOICE_LIMIT
            groups = {str(i): dict(items[start:start + width])
                      for i, start in enumerate(range(0, len(items), width))}
            selected = self._choose(state, {k: {'first_option': next(iter(v)),
                                                'last_option': list(v)[-1], 'option_count': len(v)}
                                            for k, v in groups.items()},
                                    instruction + ' First choose a group of options.')
            return self._choose(state, groups[selected], instruction)
        self.last_requests.append(deepcopy({'state': state, 'criteria': criteria, 'instructions': instruction}))
        return super()._choose(state, criteria, instruction)

    def decide(self, context):
        self.last_selection = []
        self.last_requests = []
        self.last_features = None
        obs = context.observation
        actions = list(obs.legal_actions)
        if len(actions) == 1:
            return Decision(actions[0].id, '唯一合法动作')
        state = {'rules': asdict(context.rules), 'player_id': obs.player_id,
                 'private': obs.private, 'public': obs.public,
                 'history': [asdict(e) for e in obs.history], 'turn': obs.turn}
        consequences = {}
        if self.mode == 'assisted':
            from .strategy import features
            common, consequences = features(context)
            state['belief'] = asdict(context.belief)
            state['decision_facts'] = common
            self.last_features = {'decision_facts': common, 'candidate_consequences': consequences}
        # Identical ordering, grouping and instruction in both modes. No rollout ranking,
        # mandatory pass or immediate-finish shortcut. Every legal action stays reachable.
        def criterion(action):
            value = {'label': action.label, **action.payload}
            if self.mode == 'assisted':
                value['consequences'] = {k: v for k, v in consequences[action.id].items()
                                         if k not in ('feasible_partition', 'remaining_cards')
                                         and v is not False and v != []}
            return value
        if len(actions) > CHOICE_LIMIT:
            families = {}
            for action in actions:
                families.setdefault(action.payload['kind'], []).append(action)
            key = self._choose(state, {k: {'kind': k, 'legal_action_count': len(v)}
                                      for k, v in families.items()}, INSTRUCTION + ' Choose a play family first.')
            actions = families[key]
        if len(actions) > CHOICE_LIMIT:
            bodies = {}
            for action in actions:
                p = action.payload
                key = '%s:%s:%s' % (p['kind'], p['main'], p['chain'])
                bodies.setdefault(key, []).append(action)
            key = self._choose(state, {k: {'body': k, 'legal_action_count': len(v)}
                                      for k, v in bodies.items()}, INSTRUCTION + ' Choose a body rank and length.')
            actions = bodies[key]
        while len(actions) > CHOICE_LIMIT:
            # Defensive bounded grouping, retaining every candidate.
            width = (len(actions) + CHOICE_LIMIT - 1) // CHOICE_LIMIT
            groups = {str(i): actions[start:start + width]
                      for i, start in enumerate(range(0, len(actions), width))}
            key = self._choose(state, {k: {'legal_action_count': len(v), 'first_action': v[0].label,
                                            'last_action': v[-1].label}
                                      for k, v in groups.items()}, INSTRUCTION + ' Choose an action group.')
            actions = groups[key]
        return Decision(self._choose(state, {a.id: criterion(a) for a in actions}, INSTRUCTION),
                        'jev_' + self.mode)
