"""完整牌局的简单 AI 与保留全部候选的分层 JEV 适配。"""

from collections import Counter
from dataclasses import asdict
from functools import lru_cache

from joker_jev.agents.base import Agent
from joker_jev.core.models import Decision
from joker_jev.games.doudizhu.tactics import validate_choice
from .cards import RANKS, ordered, runs


@lru_cache(maxsize=8192)
def rough_groups(hand):
    """近似出牌轮数，仅供启发式排序，不是精确求解器。"""
    counts = Counter(hand)
    for copies, minimum in ((3, 2), (2, 3), (1, 5)):
        while True:
            choices = list(runs(counts, copies, minimum))
            if not choices:
                break
            best = max(choices, key=len)
            for rank in best:
                counts[rank] -= copies
            # 移除一条连续组合后，其余组数递归近似。
            return 1 + rough_groups(ordered(counts.elements()))
    triples = sum(n >= 3 for n in counts.values())
    singles = sum(n == 1 for n in counts.values())
    pairs = sum(n == 2 for n in counts.values())
    return sum(n > 0 for n in counts.values()) - min(triples, singles + pairs)


class FullSimpleAgent(Agent):
    def decide(self, context):
        obs = context.observation
        actions = obs.legal_actions
        if len(actions) == 1:
            return Decision(actions[0].id)
        hand = obs.private['hand']
        counts = Counter(hand)
        pub = obs.public
        if pub['phase'] == 'bidding':
            strength = (3 * counts['BJ'] + 2 * counts['SJ'] + counts['2'] +
                        3 * sum(n == 4 for n in counts.values()) + max(0, 7 - rough_groups(tuple(hand))))
            desired = 3 if strength >= 9 else 2 if strength >= 6 else 1 if strength >= 3 else 0
            eligible = [a for a in actions if a.payload['bid'] <= desired]
            return Decision(max(eligible, key=lambda a: a.payload['bid']).id)
        plays = [a for a in actions if a.payload['cards']]
        finishes = [a for a in plays if len(a.payload['cards']) == len(hand)]
        if finishes:
            return Decision(finishes[0].id)
        me = obs.player_id
        landlord = pub['landlord']
        enemies = [p for p in pub['remaining_counts'] if (p == landlord) != (me == landlord)]
        urgent = any(pub['remaining_counts'][p] <= 2 for p in enemies)
        teammate = obs.private['teammate']
        if pub['target'] and pub['owner'] == teammate and not urgent:
            return Decision('pass')
        if not plays:
            return Decision('pass')
        if pub['target'] and pub['target']['kind'] == 'single' and any(pub['remaining_counts'][p] == 1 for p in enemies):
            singles = [a for a in plays if a.payload['kind'] == 'single']
            if singles:
                return Decision(max(singles, key=lambda a: a.payload['main']).id)
        if not pub['target']:
            if any(pub['remaining_counts'][p] == 1 for p in enemies):
                nonsingles = [a for a in plays if a.payload['kind'] != 'single']
                if nonsingles:
                    plays = nonsingles
            elif teammate == pub['next_player'] and pub['remaining_counts'].get(teammate) == 1:
                singles = [a for a in plays if a.payload['kind'] == 'single']
                return Decision(min(singles, key=lambda a: a.payload['main']).id)
        def score(action):
            used = Counter(action.payload['cards'])
            rest = counts - used
            broken = sum(counts[r] == 4 and 0 < used[r] < 4 for r in counts)
            broken += int(counts['SJ'] and counts['BJ'] and used['SJ'] != used['BJ'])
            bomb_cost = int(action.payload['kind'] in ('bomb', 'rocket') and not urgent)
            return (broken, bomb_cost, rough_groups(ordered(rest.elements())),
                    -len(action.payload['cards']), action.payload['main'])
        return Decision(min(plays, key=score).id, 'full_simple_v1')


def visible_payload(context):
    obs = context.observation
    return {'rules': asdict(context.rules), 'player_id': obs.player_id,
            'private': obs.private, 'public': obs.public, 'belief': asdict(context.belief),
            'history': [asdict(e) for e in obs.history], 'turn': obs.turn}


class FullJEVAgent(Agent):
    def __init__(self, backend):
        self.backend = backend
        self.last_selection = []

    def _choose(self, state, criteria, instruction):
        if len(criteria) == 1:
            return next(iter(criteria))
        if not 1 <= len(criteria) <= 255:
            raise ValueError('分层 Choice 候选数超限')
        response = self.backend.evaluate(state, {'action': {
            'type': 'choice', 'instructions': instruction, 'criteria': criteria}})
        answer = response['answers']['action']
        validate_choice(answer, criteria)
        self.last_selection.append({'choice': answer['choice'], 'confidence': answer['confidence'],
                                    'probabilities': answer['probabilities'], 'candidate_count': len(criteria)})
        return answer['choice']

    def decide(self, context):
        self.last_selection = []
        actions = list(context.observation.legal_actions)
        if len(actions) == 1:
            return Decision(actions[0].id, '唯一合法动作')
        state = visible_payload(context)
        instruction = ('Choose the legal action serving your current role and team reward. During bidding, assess your own hand. '
                       'During play, either farmer finishing is a shared farmer win. Preserve useful control, consider turn order '
                       'and remaining counts. Belief is uncertain; do not assume actual opponent hands. Bombs and spring affect stakes.')
        if len(actions) > 255:
            families = {}
            for action in actions:
                families.setdefault(action.payload['kind'], []).append(action)
            criteria = {k: {'kind': k, 'legal_action_count': len(v),
                            'body_options': sorted({(a.payload.get('main', -1), a.payload.get('chain', 1), len(a.payload['cards'])) for a in v})}
                        for k, v in families.items()}
            selected = self._choose(state, criteria, instruction + ' First choose a play family; all legal actions remain reachable.')
            actions = families[selected]
        if len(actions) > 255:
            bodies = {}
            for action in actions:
                p = action.payload
                key = '%s:%s:%s' % (p['kind'], p['main'], p['chain'])
                bodies.setdefault(key, []).append(action)
            criteria = {k: {'kind': v[0].payload['kind'], 'main_rank': RANKS[v[0].payload['main']],
                            'chain': v[0].payload['chain'], 'attachment_options': len(v)} for k, v in bodies.items()}
            selected = self._choose(state, criteria, instruction + ' Choose the body rank and chain length before its attachments.')
            actions = bodies[selected]
        # 20 张以内手牌、固定主体的合法翅膀组合不超过 C(11,3)=165。
        criteria = {a.id: {'label': a.label, **a.payload} for a in actions}
        return Decision(self._choose(state, criteria, instruction))
