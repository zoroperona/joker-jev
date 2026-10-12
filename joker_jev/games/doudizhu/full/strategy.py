"""玩家可见的手牌分解与动作后果；不读取对手实际手牌或实验标注。"""

from collections import Counter

from .cards import RANKS, ordered, all_moves


class HandPlanner:
    """有节点预算的拆牌搜索，返回一条真实可执行的无人压制拆牌方案。"""
    def __init__(self, hand, node_budget=4000):
        self.ranks = tuple(r for r in RANKS if r in hand)
        self.root = tuple(Counter(hand)[r] for r in self.ranks)
        self.patterns = []
        seen = set()
        for move in all_moves(ordered(hand)):
            if move.cards in seen:
                continue
            seen.add(move.cards)
            counts = Counter(move.cards)
            self.patterns.append((tuple(counts[r] for r in self.ranks), move))
        self.patterns.sort(key=lambda item: (-len(item[1].cards), item[1].main, item[1].kind))
        self.by_rank = [[p for p in self.patterns if p[0][i]] for i in range(len(self.ranks))]
        self.memo = {tuple(0 for _ in self.ranks): ()}
        self.node_budget = node_budget
        self.nodes = 0
        self.truncated = False

    @staticmethod
    def fits(need, available):
        return all(a <= b for a, b in zip(need, available))

    def greedy(self, counts):
        result = []
        while any(counts):
            need, move = next(p for p in self.patterns if self.fits(p[0], counts))
            result.append(move)
            counts = tuple(b - a for a, b in zip(need, counts))
        return tuple(result)

    def solve(self, counts):
        if counts in self.memo:
            return self.memo[counts]
        if self.nodes >= self.node_budget:
            self.truncated = True
            return self.greedy(counts)
        self.nodes += 1
        anchor = next(i for i, n in enumerate(counts) if n)
        best = self.greedy(counts)
        if len(best) == 1:
            self.memo[counts] = best
            return best
        for need, move in self.by_rank[anchor]:
            if not self.fits(need, counts):
                continue
            rest = tuple(b - a for a, b in zip(need, counts))
            if not any(rest):
                best = (move,)
                break
            candidate = (move,) + self.solve(rest)
            if len(candidate) < len(best):
                best = candidate
                if len(best) == 2:  # 已排除一步出完，二步已达到下界。
                    break
        self.memo[counts] = best
        return best

    def after(self, cards):
        used = Counter(cards)
        counts = tuple(n - used[r] for r, n in zip(self.ranks, self.root))
        if any(n < 0 for n in counts):
            raise ValueError('拆牌动作不是当前手牌子集')
        plan = self.solve(counts)
        return {'remaining_plays_upper_bound': len(plan),
                'feasible_partition': [{'kind': m.kind, 'cards': list(m.cards)} for m in plan]}


def features(context):
    obs = context.observation
    hand = obs.private['hand']
    counts = Counter(hand)
    planner = HandPlanner(hand)
    hand_plan = planner.after(())
    public = obs.public
    me = obs.player_id
    landlord = public['landlord']
    teammate = obs.private['teammate']
    enemies = [p for p in public['remaining_counts'] if landlord and (p == landlord) != (me == landlord)]
    unseen = Counter(context.belief.facts['unseen_card_counts'])
    target = public['target']
    responders = []
    if target:
        next_index = (int(me[1:]) + 1) % 3
        while 'p%d' % next_index != public['owner']:
            responders.append('p%d' % next_index)
            next_index = (next_index + 1) % 3
    urgent = [p for p in enemies if public['remaining_counts'][p] <= 2]
    common = {'rank_order': list(RANKS), 'self_role': obs.private['role'], 'teammate': teammate,
              'enemy_players': enemies, 'enemy_remaining_counts': {p: public['remaining_counts'][p] for p in enemies},
              'urgent_enemies': urgent, 'responders_after_pass_before_owner_returns': responders,
              'hand_partition': hand_plan, 'hand_controls': {'jokers': counts['SJ'] + counts['BJ'], 'twos': counts['2'],
                                                           'bomb_ranks': [r for r in counts if counts[r] == 4]},
              'semantics': 'Partitions are feasible ways to empty your own hand ONLY if nobody interferes, not win forecasts. Hidden-card response flags mean possible, not certain. No actual opponent hands are used.'}
    result = {}
    for action in obs.legal_actions:
        if public['phase'] == 'bidding':
            bid = action.payload['bid']
            result[action.id] = {'bid': bid, 'landlord_loss_base_before_multipliers': 2 * bid,
                                 'unknown_bottom_cards': 3, 'does_not_guarantee_landlord': bid != 3}
            continue
        cards = tuple(action.payload['cards'])
        used = Counter(cards)
        rest = counts - used
        passing = not cards
        estimate = planner.after(cards)
        rank = action.payload.get('main')
        basic_unbeatable = False
        if action.payload['kind'] in ('single', 'pair'):
            copies = len(cards)
            higher = any(unseen[r] >= copies for r in RANKS[rank + 1:])
            bomb_possible = any(n >= 4 for n in unseen.values()) or (unseen['SJ'] and unseen['BJ'])
            basic_unbeatable = not higher and not bomb_possible
        enemy_can_finish_after_pass = []
        if target and target['kind'] == 'single':
            for p in responders:
                if p in enemies and public['remaining_counts'][p] == 1 and any(unseen[r] for r in RANKS[target['main'] + 1:]):
                    enemy_can_finish_after_pass.append(p)
        result[action.id] = {**estimate, 'remaining_cards': list(ordered(rest.elements())),
                             'finishes_own_hand': bool(cards) and not rest,
                             'takes_teammate_control': bool(cards) and public['owner'] == teammate and teammate is not None,
                             'passes_to_enemy_owner': passing and public['passes'] == 1 and public['owner'] in enemies,
                             'enemy_may_finish_after_pass': enemy_can_finish_after_pass if passing else [],
                             'higher_basic_play_impossible_from_unseen_pool': basic_unbeatable,
                             'remaining_jokers': rest['SJ'] + rest['BJ'], 'remaining_twos': rest['2'],
                             'broken_bomb_ranks': [r for r in counts if counts[r] == 4 and 0 < used[r] < 4],
                             'split_triple_ranks': [r for r in counts if counts[r] == 3 and 0 < used[r] < 3],
                             'split_pair_ranks': [r for r in counts if counts[r] == 2 and used[r] == 1],
                             'uses_bomb_multiplier': action.payload['kind'] in ('bomb', 'rocket')}
    common['partition_search'] = {'nodes': planner.nodes, 'budget': planner.node_budget, 'budget_exhausted': planner.truncated,
                                  'guarantee': 'Every partition is legal for the original hand. Counts are upper bounds; no optimality claim if budget exhausted.'}
    return common, result
