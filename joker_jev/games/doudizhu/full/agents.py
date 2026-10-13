"""完整牌局的简单 AI 与保留全部候选的分层 JEV 适配。"""

from collections import Counter
from dataclasses import asdict

from joker_jev.agents.base import Agent
from joker_jev.agents.typesafe import TypeSafeError
from joker_jev.core.models import Decision
from joker_jev.games.doudizhu.tactics import validate_choice
from .cards import RANKS, Move, ordered
from .rollout import rough_groups, simple_play


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
        players = ('p0', 'p1', 'p2')
        target = pub['target']
        move = simple_play(ordered(hand), Move(tuple(target['cards']), target['kind'], target['main'], target['chain']) if target else None,
                           players.index(pub['owner']) if pub['owner'] is not None else None,
                           players.index(obs.player_id), players.index(pub['landlord']),
                           [pub['remaining_counts'][p] for p in players])
        return Decision(move.id if move else 'pass', 'full_simple_v1')


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
        try:
            validate_choice(answer, criteria)
        except TypeSafeError:
            self.last_selection.append({'status': 'invalid_response', 'answer': answer,
                                        'candidate_ids': list(criteria), 'candidate_count': len(criteria)})
            raise
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


STRATEGIC_INSTRUCTIONS = (
    "Choose the legal action for your team's eventual win and score, not simply the largest current play. "
    "During bidding balance controls, feasible hand structure and unknown bottom cards against doubled landlord liability; no bid is mandated. "
    "During play read decision_facts and each action's consequences. A partition is only a feasible plan if nobody beats you, NOT a win probability. "
    "Plan the order: get low cards out while retaining cards that can regain the lead; spending all jokers/twos first can strand low singles. "
    "A longer combination may leave a worse hand structure. Leading a bomb merely to keep a lead you already own spends future control and doubles stakes. "
    "A farmer may yield to a teammate, but check actual responder order and urgent enemies before passing. "
    "If an opponent has one card, inspect blocking plays before giving that opponent a free lead or a chance to finish. "
    "Do not take a teammate's lead without a concrete team benefit. Prefer immediate team victory. "
    "These are conditional considerations, not mandatory actions. Any offered legal action may be selected."
)


class StrategicJEVAgent(FullJEVAgent):
    """v2：提供可见动作后果与拆牌方案，最终合法动作仍由 JEV 选择。"""
    choice_limit = 255
    compact = False

    def decide(self, context):
        from .strategy import features
        self.last_selection = []
        self.last_features = None
        actions = list(context.observation.legal_actions)
        if len(actions) == 1:
            return Decision(actions[0].id, '唯一合法动作')
        common, consequences = features(context)
        self.last_features = {'decision_facts': common, 'candidate_consequences': consequences}
        state = visible_payload(context)
        state['decision_facts'] = common
        if len(actions) > self.choice_limit:
            families = {}
            for a in actions:
                families.setdefault(a.payload['kind'], []).append(a)
            def summarize_group(group):
                return {'legal_action_count': len(group),
                        'best_remaining_plays_upper_bound': min(consequences[a.id]['remaining_plays_upper_bound'] for a in group),
                        'has_immediate_finish': any(consequences[a.id]['finishes_own_hand'] for a in group),
                        'body_options': sorted({(a.payload.get('main', -1), a.payload.get('chain', 1), len(a.payload['cards'])) for a in group})}
            key = self._choose(state, {k: summarize_group(v) for k, v in families.items()},
                               STRATEGIC_INSTRUCTIONS + ' First choose a play family; all actions remain reachable.')
            actions = families[key]
            if len(actions) > self.choice_limit:
                bodies = {}
                for a in actions:
                    key = '%s:%s:%s' % (a.payload['kind'], a.payload['main'], a.payload['chain'])
                    bodies.setdefault(key, []).append(a)
                key = self._choose(state, {k: summarize_group(v) for k, v in bodies.items()},
                                   STRATEGIC_INSTRUCTIONS + ' Choose body rank and chain length, then attachments.')
                actions = bodies[key]
        while len(actions) > self.choice_limit:
            pages = {str(i // self.choice_limit): actions[i:i + self.choice_limit]
                     for i in range(0, len(actions), self.choice_limit)}
            options = {key: {**summarize_group(group),
                             'first_action': group[0].label, 'last_action': group[-1].label}
                       for key, group in pages.items()}
            key = self._choose(state, options, STRATEGIC_INSTRUCTIONS + ' Choose a bounded attachment group; no legal action has been removed.')
            actions = pages[key]
        def consequence(action):
            if not self.compact:
                return consequences[action.id]
            return {k: v for k, v in consequences[action.id].items()
                    if k not in ('feasible_partition', 'remaining_cards') and v is not False and v != []}
        criteria = {a.id: {'label': a.label, **a.payload, 'consequences': consequence(a)} for a in actions}
        return Decision(self._choose(state, criteria, STRATEGIC_INSTRUCTIONS))


class CompactStrategicJEVAgent(StrategicJEVAgent):
    """v2_compact：每次最终动作 Choice 至多 24 项，省略重复残余牌列表。"""
    choice_limit = 24
    compact = True


class RolloutAgent(Agent):
    """纯代码基线：叫分和出牌都取玩家视角模拟估计最好的动作，用于离线验证模拟信号。"""
    def __init__(self, rollouts=600, bid_rollouts=200, bid_margin=0.0):
        self.rollouts, self.bid_rollouts, self.bid_margin = rollouts, bid_rollouts, bid_margin

    def decide(self, context):
        from .rollout import evaluate_bidding, evaluate_plays
        actions = context.observation.legal_actions
        if len(actions) == 1:
            return Decision(actions[0].id)
        if context.observation.public['phase'] == 'bidding':
            values = evaluate_bidding(context, self.bid_rollouts)
            lord = values['if_self_landlord']['mean_score_per_bid_point']
            farmer = values['if_other_landlord']['mean_score_per_bid_point']
            if lord > max(farmer, 0) + self.bid_margin:
                return Decision(max(actions, key=lambda a: a.payload['bid']).id, 'rollout_bid')
            return Decision('bid:0', 'rollout_bid')
        values = evaluate_plays(context, actions, self.rollouts)
        best = max(values, key=lambda k: (values[k]['samples'], values[k]['mean_score'], values[k]['team_win_rate']))
        return Decision(best, 'rollout_play')


SIMULATION_INSTRUCTIONS = STRATEGIC_INSTRUCTIONS + (
    " Each candidate may carry `simulation`: from YOUR view only, unseen cards were dealt at random consistent with public "
    "counts and revealed bottom cards, and the game was played out with every seat using a simple heuristic policy. "
    "team_win_rate and mean_score (your own score incl. bid and multipliers) are noisy estimates over `samples` worlds, "
    "not facts about the real hands. Candidates are listed best simulated first. Prefer higher mean_score unless you see a "
    "concrete reason the simple-policy playout misjudges this position. During bidding, compare the simulated score of being "
    "landlord at each bid with the score of letting another player become landlord."
)


class SimulationJEVAgent(CompactStrategicJEVAgent):
    """v3：在 v2_compact 后果之上加入玩家视角采样模拟；立即出完时直接出完，最终选择仍由 JEV 做出。"""
    rollouts = 600
    bid_rollouts = 200
    recent_events = 6

    def decide(self, context):
        from .rollout import evaluate_bidding, evaluate_plays
        from .strategy import features
        self.last_selection = []
        self.last_features = None
        obs = context.observation
        actions = list(obs.legal_actions)
        if len(actions) == 1:
            return Decision(actions[0].id, '唯一合法动作')
        common, consequences = features(context)
        bidding = obs.public['phase'] == 'bidding'
        if bidding:
            values = evaluate_bidding(context, self.bid_rollouts)
            common['bidding_simulation'] = values
            per_point = values['if_self_landlord']['mean_score_per_bid_point']
            for a in actions:
                bid = a.payload['bid']
                consequences[a.id]['simulated_score_if_landlord_at_this_bid'] = round(bid * per_point, 3) if bid else None
            simulation = {}
        else:
            simulation = evaluate_plays(context, actions, self.rollouts)
            for a in actions:
                if a.id in simulation:
                    consequences[a.id]['simulation'] = simulation[a.id]
            actions.sort(key=lambda a: (-simulation[a.id]['samples'], -simulation[a.id]['mean_score'],
                                        -simulation[a.id]['team_win_rate']))
        self.last_features = {'decision_facts': common, 'candidate_consequences': consequences,
                              'simulation_config': {'rollouts': self.rollouts, 'bid_rollouts': self.bid_rollouts,
                                                    'policy': 'full_simple_v1 for all seats'}}
        finishes = [a for a in actions if consequences[a.id].get('finishes_own_hand')]
        if finishes:
            # 立即出完必胜；多种出完方式时取模拟积分最高（炸弹倍数）。
            best = max(finishes, key=lambda a: simulation[a.id]['mean_score'])
            return Decision(best.id, '立即出完，代码直接选择')
        state = visible_payload(context)
        state['history'] = state['history'][-self.recent_events:]
        state['decision_facts'] = common
        def criterion(a):
            c = {k: v for k, v in consequences[a.id].items()
                 if k not in ('feasible_partition', 'remaining_cards') and v is not False and v != []}
            return {'label': a.label, **a.payload, 'consequences': c}
        if len(actions) <= self.choice_limit:
            return Decision(self._choose(state, {a.id: criterion(a) for a in actions}, SIMULATION_INSTRUCTIONS))
        top, rest = actions[:self.choice_limit - 1], actions[self.choice_limit - 1:]
        criteria = {a.id: criterion(a) for a in top}
        criteria['more_options'] = {'label': 'Show the %d other legal actions (lower simulated value)' % len(rest),
                                    'best_simulated_mean_score_among_them': max(simulation[a.id]['mean_score'] for a in rest)}
        key = self._choose(state, criteria, SIMULATION_INSTRUCTIONS + ' `more_options` keeps every other legal action reachable.')
        if key != 'more_options':
            return Decision(key)
        while len(rest) > self.choice_limit:
            pages = {str(i // self.choice_limit): rest[i:i + self.choice_limit] for i in range(0, len(rest), self.choice_limit)}
            options = {k: {'legal_action_count': len(g), 'first_action': g[0].label, 'last_action': g[-1].label,
                           'best_simulated_mean_score': max(simulation[a.id]['mean_score'] for a in g)}
                       for k, g in pages.items()}
            rest = pages[self._choose(state, options, SIMULATION_INSTRUCTIONS + ' Choose a bounded group; no legal action has been removed.')]
        return Decision(self._choose(state, {a.id: criterion(a) for a in rest}, SIMULATION_INSTRUCTIONS))


JEV_STRATEGIES = {'v1': FullJEVAgent, 'v2': StrategicJEVAgent, 'v2_compact': CompactStrategicJEVAgent,
                  'v3': SimulationJEVAgent}
