"""完整斗地主牌型。花色不影响玩法，实体重数由牌堆计数限制。"""

from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations

RANKS = tuple('3 4 5 6 7 8 9 10 J Q K A 2 SJ BJ'.split())
DECK = tuple(r for r in RANKS for _ in range(1 if r in ('SJ', 'BJ') else 4))
KINDS = ('single', 'pair', 'triple', 'triple_single', 'triple_pair', 'straight',
         'pair_straight', 'airplane', 'airplane_single', 'airplane_pair',
         'four_two_single', 'four_two_pair', 'bomb', 'rocket')


def ordered(cards):
    return tuple(sorted(cards, key=RANKS.index))


@dataclass(frozen=True)
class Move:
    cards: tuple
    kind: str
    main: int
    chain: int = 1

    @property
    def id(self):
        return '%s:%d:%d:%s' % (self.kind, self.main, self.chain, ','.join(self.cards))

    @property
    def body(self):
        return '%s:%d:%d' % (self.kind, self.main, self.chain)


def beats(move, target):
    if target is None:
        return True
    if move.kind == 'rocket':
        return target.kind != 'rocket'
    if target.kind == 'rocket':
        return False
    if move.kind == 'bomb' and target.kind != 'bomb':
        return True
    return (move.kind == target.kind and move.chain == target.chain and
            len(move.cards) == len(target.cards) and move.main > target.main)


def runs(counts, copies, minimum):
    for start in range(12):  # 只能 3 至 A；2 和王不能进入连续主体。
        for end in range(start, 12):
            if counts[RANKS[end]] < copies:
                break
            if end - start + 1 >= minimum:
                yield tuple(RANKS[start:end + 1])


def single_wings(counts, width):
    """单翅可带对子，每点最多两张；不允许同时带双王。"""
    ranks = [r for r in RANKS if counts[r]]
    def visit(index, left, selected):
        if left == 0:
            if not ('SJ' in selected and 'BJ' in selected):
                yield tuple(selected)
            return
        if index == len(ranks) or sum(min(2, counts[r]) for r in ranks[index:]) < left:
            return
        rank = ranks[index]
        for n in range(min(2, counts[rank], left) + 1):
            yield from visit(index + 1, left - n, selected + [rank] * n)
    yield from visit(0, width, [])


@lru_cache(maxsize=2048)
def all_moves(hand):
    counts = Counter(hand)
    if counts - Counter(DECK):
        raise ValueError('手牌超出牌堆')
    found = set()
    def add(cards, kind, main, chain=1):
        found.add(Move(ordered(cards), kind, RANKS.index(main), chain))
    for rank in RANKS:
        n = counts[rank]
        if n:
            add((rank,), 'single', rank)
        if n >= 2:
            add((rank,) * 2, 'pair', rank)
        if n >= 3:
            add((rank,) * 3, 'triple', rank)
            for wing in RANKS:
                if wing == rank:
                    continue
                if counts[wing]:
                    add((rank,) * 3 + (wing,), 'triple_single', rank)
                if counts[wing] >= 2:
                    add((rank,) * 3 + (wing,) * 2, 'triple_pair', rank)
        if n == 4:
            add((rank,) * 4, 'bomb', rank)
            rest = counts.copy()
            del rest[rank]
            for wings in single_wings(rest, 2):
                add((rank,) * 4 + wings, 'four_two_single', rank)
            for a, b in combinations([r for r in RANKS if rest[r] >= 2], 2):
                add((rank,) * 4 + (a, a, b, b), 'four_two_pair', rank)
    if counts['SJ'] and counts['BJ']:
        add(('SJ', 'BJ'), 'rocket', 'BJ')
    for copies, minimum, kind in ((1, 5, 'straight'), (2, 3, 'pair_straight'), (3, 2, 'airplane')):
        for run in runs(counts, copies, minimum):
            body = tuple(r for r in run for _ in range(copies))
            add(body, kind, run[-1], len(run))
            if copies != 3:
                continue
            # 翅膀不允许使用主体点数的第四张。
            rest = Counter({r: n for r, n in counts.items() if r not in run})
            for wings in single_wings(rest, len(run)):
                add(body + wings, 'airplane_single', run[-1], len(run))
            for ranks in combinations([r for r in RANKS if rest[r] >= 2], len(run)):
                wings = tuple(r for r in ranks for _ in range(2))
                add(body + wings, 'airplane_pair', run[-1], len(run))
    return tuple(sorted(found, key=lambda m: (KINDS.index(m.kind), m.chain, m.main, m.cards)))


def legal_moves(hand, target=None):
    return tuple(m for m in all_moves(ordered(hand)) if beats(m, target))


def classify(cards):
    """所有使用完整输入牌的合法解释；空结果表示非法牌型。"""
    hand = ordered(cards)
    return tuple(m for m in all_moves(hand) if m.cards == hand)
