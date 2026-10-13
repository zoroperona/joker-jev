"""玩家视角的隐藏牌采样与快速对局模拟；只读取公开信息和自己的手牌。

每个“世界”把未见牌随机分给其他玩家（地主已公开的底牌固定在地主手中），
随后三家都用 simple_play 打完。结果是对该对手模型的估计，不是真实胜率。
"""

from collections import Counter
import hashlib
import json
import random

from functools import lru_cache

from .cards import DECK, RANKS, Move, ordered, legal_moves

PLAYERS = ('p0', 'p1', 'p2')
INDEX = {r: i for i, r in enumerate(RANKS)}
SJ, BJ = INDEX['SJ'], INDEX['BJ']


def _vector(cards):
    counts = [0] * len(RANKS)
    for card in cards:
        counts[INDEX[card]] += 1
    return tuple(counts)


def rough_groups(hand):
    """近似出牌轮数，仅供启发式排序，不是精确求解器。"""
    return _groups(_vector(hand))


@lru_cache(maxsize=262144)
def _groups(counts):
    for copies, minimum in ((3, 2), (2, 3), (1, 5)):
        # 最长连续段（3 至 A），并列取最早开始者。
        best_start, best_len, start = -1, 0, None
        for i in range(13):
            if i < 12 and counts[i] >= copies:
                if start is None:
                    start = i
            elif start is not None:
                if i - start > best_len:
                    best_start, best_len = start, i - start
                start = None
        if best_len >= minimum:
            rest = list(counts)
            for i in range(best_start, best_start + best_len):
                rest[i] -= copies
            # 移除一条连续组合后，其余组数递归近似。
            return 1 + _groups(tuple(rest))
    triples = sum(n >= 3 for n in counts)
    singles = sum(n == 1 for n in counts)
    pairs = sum(n == 2 for n in counts)
    return sum(n > 0 for n in counts) - min(triples, singles + pairs)


def simple_play(hand, target, owner, me, landlord, remaining):
    """FullSimpleAgent 的出牌规则（纯函数）；返回 Move，None 表示过牌。"""
    moves = legal_moves(hand, target)
    if not moves:
        return None
    if len(moves) == 1 and target is None:
        return moves[0]
    finishes = [m for m in moves if len(m.cards) == len(hand)]
    if finishes:
        return finishes[0]
    enemies = [p for p in range(3) if p != me and (p == landlord) != (me == landlord)]
    urgent = any(remaining[p] <= 2 for p in enemies)
    teammate = next((p for p in range(3) if p != me and p != landlord), None) if me != landlord else None
    if target is not None and owner == teammate and not urgent:
        return None
    if target is not None and target.kind == 'single' and any(remaining[p] == 1 for p in enemies):
        singles = [m for m in moves if m.kind == 'single']
        if singles:
            return max(singles, key=lambda m: m.main)
    no_singles = False
    if target is None:
        if any(remaining[p] == 1 for p in enemies):
            no_singles = any(m.kind != 'single' for m in moves)
        elif teammate == (me + 1) % 3 and remaining[teammate] == 1:
            return min((m for m in moves if m.kind == 'single'), key=lambda m: m.main)
    return _best_play(hand, target, urgent, no_singles)


@lru_cache(maxsize=262144)
def _best_play(hand, target, urgent, no_singles):
    plays = [m for m in legal_moves(hand, target) if not (no_singles and m.kind == 'single')]
    counts = _vector(hand)
    rocket = counts[SJ] and counts[BJ]
    def score(move):
        used = _vector(move.cards)
        rest = tuple(a - b for a, b in zip(counts, used))
        broken = sum(n == 4 and 0 < u < 4 for n, u in zip(counts, used))
        broken += int(rocket and used[SJ] != used[BJ])
        bomb_cost = int(move.kind in ('bomb', 'rocket') and not urgent)
        return (broken, bomb_cost, _groups(rest), -len(move.cards), move.main)
    return min(plays, key=score)


def simulate(hands, actor, landlord, bid, target=None, owner=None, passes=0, bombs=0, play_counts=(0, 0, 0),
             max_steps=400):
    """从出牌阶段任意状态快速打完；返回各座位积分（与 FullDoudizhuGame 相同公式）。"""
    hands = [tuple(h) for h in hands]
    counts = list(play_counts)
    for _ in range(max_steps):
        remaining = [len(h) for h in hands]
        move = simple_play(hands[actor], target, owner, actor, landlord, remaining)
        if move is None:
            if passes == 1:
                actor, target, owner, passes = owner, None, None, 0
            else:
                actor, passes = (actor + 1) % 3, 1
            continue
        rest = Counter(hands[actor]) - Counter(move.cards)
        hands[actor] = ordered(rest.elements())
        counts[actor] += 1
        bombs += move.kind in ('bomb', 'rocket')
        if not hands[actor]:
            won = actor == landlord
            spring = (all(counts[i] == 0 for i in range(3) if i != landlord) if won else counts[landlord] == 1)
            unit = bid * 2 ** (bombs + int(spring))
            sign = 1 if won else -1
            return [float(sign * unit * (2 if i == landlord else -1)) for i in range(3)]
        target, owner, passes, actor = move, actor, 0, (actor + 1) % 3
    raise RuntimeError('模拟超过步数上限')


def _view_seed(context, salt=''):
    """随机源只由玩家可见信息决定：隐藏牌不同的同一视角得到相同采样。"""
    obs = context.observation
    text = json.dumps([obs.player_id, obs.private, obs.public, salt], sort_keys=True, default=str)
    return int(hashlib.sha256(text.encode()).hexdigest()[:16], 16)


class WorldSampler:
    """按公开约束采样其他两家手牌（以及叫分阶段的底牌）。"""
    def __init__(self, context):
        obs = context.observation
        pub = obs.public
        self.me = PLAYERS.index(obs.player_id)
        hand = Counter(obs.private['hand'])
        played = Counter(c for cards in pub['played'].values() for c in cards)
        pool = Counter(DECK) - hand - played
        landlord = pub['landlord']
        self.landlord = PLAYERS.index(landlord) if landlord is not None else None
        self.known = Counter()
        if landlord is not None and self.landlord != self.me:
            self.known = Counter(pub['bottom_cards']) - Counter(pub['played'][landlord])
        self.pool = ordered((pool - self.known).elements())
        self.sizes = {i: pub['remaining_counts'][p] for i, p in enumerate(PLAYERS) if i != self.me}
        if self.landlord in self.sizes:
            self.sizes[self.landlord] -= sum(self.known.values())
        self.hand = ordered(obs.private['hand'])
        self.bottom_hidden = pub['phase'] == 'bidding'

    def sample(self, rng):
        cards = list(self.pool)
        rng.shuffle(cards)
        hands = [None, None, None]
        hands[self.me] = self.hand
        start = 0
        for i in sorted(self.sizes):
            extra = tuple(self.known.elements()) if i == self.landlord else ()
            hands[i] = ordered(tuple(cards[start:start + self.sizes[i]]) + extra)
            start += self.sizes[i]
        bottom = ordered(cards[start:start + 3]) if self.bottom_hidden else ()
        return hands, bottom


def _move_of(payload):
    return Move(tuple(payload['cards']), payload['kind'], payload['main'], payload['chain'])


def evaluate_plays(context, actions, rollouts=600, min_worlds=4):
    """对出牌候选做逐轮减半的模拟；共享世界样本以降低方差（common random numbers）。

    返回 {action_id: {'samples', 'team_win_rate', 'mean_score'}}；被提前淘汰的候选样本更少。
    """
    obs = context.observation
    pub = obs.public
    sampler = WorldSampler(context)
    me, landlord = sampler.me, sampler.landlord
    target = _move_of(pub['target']) if pub['target'] else None
    owner = PLAYERS.index(pub['owner']) if pub['owner'] is not None else None
    counts = tuple(pub['play_counts'][p] for p in PLAYERS)
    rng = random.Random(_view_seed(context, 'plays'))
    worlds = []
    stats = {a.id: [0, 0, 0.0] for a in actions}  # samples, wins, score sum

    def world(k):
        while len(worlds) <= k:
            worlds.append(sampler.sample(rng)[0])
        return worlds[k]

    def run(action, k):
        hands = list(world(k))
        cards = tuple(action.payload['cards'])
        if not cards:
            if pub['passes'] == 1:
                start = (owner, None, None, 0)
            else:
                start = ((me + 1) % 3, target, owner, 1)
            result = simulate(hands, start[0], landlord, pub['bid_score'], start[1], start[2], start[3],
                              pub['bombs'], counts)
        else:
            move = _move_of(action.payload)
            hands[me] = ordered((Counter(hands[me]) - Counter(cards)).elements())
            play = list(counts)
            play[me] += 1
            bombs = pub['bombs'] + (move.kind in ('bomb', 'rocket'))
            if not hands[me]:
                won = me == landlord
                spring = (all(play[i] == 0 for i in range(3) if i != landlord) if won else play[landlord] == 1)
                unit = pub['bid_score'] * 2 ** (bombs + int(spring))
                result = [float((1 if won else -1) * unit * (2 if i == landlord else -1)) for i in range(3)]
            else:
                result = simulate(hands, (me + 1) % 3, landlord, pub['bid_score'], move, me, 0, bombs, play)
        row = stats[action.id]
        row[0] += 1
        row[1] += result[me] > 0
        row[2] += result[me]

    alive = list(actions)
    per = max(min_worlds, rollouts // max(1, len(alive) * 2))
    used = 0
    while True:
        for action in alive:
            for k in range(stats[action.id][0], per):
                run(action, k)
                used += 1
        if len(alive) <= 2 or used >= rollouts:
            break
        alive.sort(key=lambda a: -stats[a.id][2] / stats[a.id][0])
        alive = alive[:max(2, len(alive) // 2)]
        per = per * 2
        # 下一轮至多用掉剩余预算。
        per = min(per, stats[alive[0].id][0] + max(1, (rollouts - used) // len(alive)))
    return {k: {'samples': n, 'team_win_rate': round(w / n, 3), 'mean_score': round(s / n, 3)}
            for k, (n, w, s) in stats.items() if n}


def evaluate_bidding(context, rollouts=200):
    """估计自己若成为地主（底牌随机）以及他人成为地主时，每 1 分叫分的积分与胜率。"""
    sampler = WorldSampler(context)
    me = sampler.me
    rng = random.Random(_view_seed(context, 'bidding'))
    landlord_rows, farmer_rows = [], []
    for k in range(rollouts):
        hands, bottom = sampler.sample(rng)
        if k % 2 == 0:
            lord = me
        else:
            lord = [i for i in range(3) if i != me][(k // 2) % 2]
        hands = list(hands)
        hands[lord] = ordered(hands[lord] + bottom)
        score = simulate(hands, lord, lord, 1)[me]
        (landlord_rows if lord == me else farmer_rows).append(score)
    def summary(rows):
        return {'samples': len(rows), 'team_win_rate': round(sum(r > 0 for r in rows) / len(rows), 3),
                'mean_score_per_bid_point': round(sum(rows) / len(rows), 3)}
    return {'if_self_landlord': summary(landlord_rows), 'if_other_landlord': summary(farmer_rows)}
