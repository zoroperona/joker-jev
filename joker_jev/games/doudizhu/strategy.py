"""有限小残局的确定规则、玩家视角与战术特征。"""

from collections import Counter
from dataclasses import asdict, dataclass
from functools import lru_cache
from itertools import combinations
from typing import Optional, Tuple

from joker_jev.core.models import Action

RANKS = tuple("3 4 5 6 7 8 9 10 J Q K A 2 SJ BJ".split())
SEATS = ("landlord", "farmer_after", "farmer_before")
DECK = Counter({r: 1 if r in ("SJ", "BJ") else 4 for r in RANKS})


def ordered(cards):
    return tuple(sorted(cards, key=RANKS.index))


def kind(cards):
    if len(cards) == 1:
        return "single"
    if cards == ("SJ", "BJ"):
        return "rocket"
    if len(cards) == 2 and cards[0] == cards[1]:
        return "pair"
    raise ValueError("当前残局只支持单牌、对子和王炸")


def beats(cards, target):
    if not target:
        return True
    if kind(cards) == "rocket":
        return kind(target) != "rocket"
    return kind(cards) == kind(target) and RANKS.index(cards[0]) > RANKS.index(target[0])


def moves(hand, target=()):
    counts = Counter(hand)
    candidates = [(r,) for r in RANKS if counts[r]]
    candidates += [(r, r) for r in RANKS if counts[r] >= 2]
    if counts["SJ"] and counts["BJ"]:
        candidates.append(("SJ", "BJ"))
    return tuple(c for c in candidates if beats(c, target)) + (((),) if target else ())


def action_id(cards):
    return "play:" + ",".join(cards) if cards else "pass"


@dataclass(frozen=True)
class Position:
    hands: Tuple[Tuple[str, ...], ...]
    actor: int
    target: Tuple[str, ...] = ()
    owner: Optional[int] = None
    passes: int = 0

    def validate(self):
        if len(self.hands) != 3 or self.actor not in range(3):
            raise ValueError("需要三个座位和有效的行动玩家")
        counts = Counter(c for hand in self.hands for c in hand)
        if any(not 1 <= len(h) <= 4 for h in self.hands):
            raise ValueError("测试快照要求每人 1 至 4 张剩余手牌")
        if any(c not in RANKS for c in counts):
            raise ValueError("未知牌")
        # 排除任何兼容底牌分配中的三张/炸弹，保证 moves 在此子域完整。
        if any(n > min(2, DECK[c]) for c, n in counts.items()):
            raise ValueError("剩余牌池每个普通点数最多两张，王各一张")
        if self.target:
            kind(self.target)
            if self.owner not in range(3) or self.passes not in (0, 1):
                raise ValueError("当前领牌者或连续过牌数无效")
            if self.actor != (self.owner + 1 + self.passes) % 3:
                raise ValueError("出牌顺序与过牌数不一致")
            counts.update(self.target)
            if any(n > DECK[c] for c, n in counts.items()):
                raise ValueError("桌面牌与剩余牌超出牌堆数量")
        elif self.owner is not None or self.passes:
            raise ValueError("自由领出时不应有未结算的领牌者或过牌")

    def advance(self, cards):
        if cards not in moves(self.hands[self.actor], self.target):
            raise ValueError("非法动作")
        if not cards:
            if self.passes == 1:
                return Position(self.hands, self.owner)
            return Position(self.hands, (self.actor + 1) % 3, self.target, self.owner, 1)
        hand = list(self.hands[self.actor])
        for c in cards:
            hand.remove(c)
        hands = list(self.hands)
        hands[self.actor] = tuple(hand)
        return Position(tuple(hands), (self.actor + 1) % 3, cards, self.actor)


@lru_cache(maxsize=None)
def landlord_wins(position):
    """全知、农民共享目标的 minimax；仅作离线诊断，不给模型。"""
    for seat, hand in enumerate(position.hands):
        if not hand:
            return seat == 0
    values = (landlord_wins(position.advance(c))
              for c in moves(position.hands[position.actor], position.target))
    return any(values) if position.actor == 0 else all(values)


def oracle_actions(position):
    return tuple(action_id(c) for c in moves(position.hands[position.actor], position.target)
                 if landlord_wins(position.advance(c)) == (position.actor == 0))


def infer_unseen(unseen, sizes, target):
    """只由未知牌池和公开牌数推断；按实体牌均匀分配，保留重复牌权重。"""
    pool = tuple(unseen.elements())
    seats = tuple(sizes)
    result = {seat: {"pair_hand_probability": 0.0,
                     "can_beat_active_play_probability": 0.0} for seat in seats}
    worlds = 0
    for selected in combinations(range(len(pool)), sizes[seats[0]]):
        selected = set(selected)
        hands = (ordered(c for i, c in enumerate(pool) if i in selected),
                 ordered(c for i, c in enumerate(pool) if i not in selected))
        worlds += 1
        for seat, hand in zip(seats, hands):
            result[seat]["pair_hand_probability"] += int(len(hand) == 2 and hand[0] == hand[1])
            result[seat]["can_beat_active_play_probability"] += int(
                bool(target) and any(m for m in moves(hand, target)))
    for values in result.values():
        for key in values:
            values[key] /= worlds
        if not target:
            del values["can_beat_active_play_probability"]
    return result


def control_facts(state):
    """由可见状态推导可能/不可能；不访问实际底牌或战术标注。"""
    active = state["public"]["active_play"]
    target = tuple(active["cards"])
    if not target:
        return {"active_play_exists": False}
    actor = state["self"]["seat"]
    owner = active["owner"]
    counts = state["public"]["remaining_counts"]
    unseen = Counter(state["belief"]["facts"]["unseen_card_counts"])
    pool_responses = tuple(c for c in moves(tuple(unseen.elements()), target) if c)
    possible = {}
    for seat in SEATS:
        responses = (tuple(c for c in moves(tuple(state["self"]["hand"]), target) if c)
                     if seat == actor else tuple(c for c in pool_responses if len(c) <= counts[seat]))
        possible[seat] = {
            "can_possibly_beat_active_play": bool(responses),
            "can_possibly_finish_by_beating_active_play": any(len(c) == counts[seat] for c in responses),
        }
    responders = []
    index = (SEATS.index(actor) + 1) % 3
    while SEATS[index] != owner:
        responders.append(SEATS[index])
        index = (index + 1) % 3
    teams = state["rules"]["team"]
    enemies = [seat for seat in responders if teams[seat] != teams[actor]]
    return {
        "active_play_exists": True,
        "active_owner_is_teammate": owner == state["self"]["teammate"],
        "responders_after_self_pass_before_owner_returns": responders,
        "passing_ends_trick": active["consecutive_passes"] == 1,
        "response_possibilities": possible,
        "opponent_can_possibly_beat_current_play_after_self_pass": any(
            possible[p]["can_possibly_beat_active_play"] for p in enemies),
        "opponent_can_possibly_finish_on_current_play_after_self_pass": any(
            possible[p]["can_possibly_finish_by_beating_active_play"] for p in enemies),
        "semantics": "Possibility over all unseen-card assignments consistent with public counts, not actual holdings or probabilities. False rules out the event; true does not guarantee it. Responders are for the unchanged active play after self passes. A previously passing player may respond again after a new higher play. No field mandates a tactical action.",
    }


def player_state(position, include_control_facts=False):
    position.validate()
    actor = position.actor
    hand = position.hands[actor]
    remaining = Counter(c for h in position.hands for c in h)
    played = DECK - remaining
    unseen = remaining - Counter(hand)
    actions = []
    for cards in moves(hand, position.target):
        rest = list(hand)
        for c in cards:
            rest.remove(c)
        actions.append(asdict(Action(action_id(cards), "过牌" if not cards else "出 " + " ".join(cards), {
            "cards": list(cards), "kind": kind(cards) if cards else "pass",
            "finishes_own_hand": bool(cards) and not rest,
            "breaks_pair": len(cards) == 1 and Counter(hand)[cards[0]] == 2,
            "remaining_hand": rest,
            "minimum_uncontested_plays": min_plays(ordered(rest)),
        })))
    state = {
        "rules": {
            "game": "doudizhu_endgame_v1", "rank_order": list(RANKS),
            "turn_order": list(SEATS),
            "team": {"landlord": "landlord", "farmer_after": "farmers", "farmer_before": "farmers"},
            "reward": "Landlord wins: landlord +1, each farmer -1; either farmer finishes: both farmers +1, landlord -1. No tactical bonus.",
            "play": "Beat the active play with the same type and a higher rank, or rocket. Passing allowed only when responding. After two passes the owner leads freely. The first empty hand ends the game immediately.",
            "scope": "Each remaining hand has at most 4 cards; the remaining pool has at most 2 cards per ordinary rank. Only singles, pairs and rocket can occur. No bidding, multipliers or spring bonuses.",
        },
        "self": {"seat": SEATS[actor], "role": "landlord" if actor == 0 else "farmer",
                 "hand": list(hand), "teammate": SEATS[3 - actor] if actor else None,
                 "next_seat": SEATS[(actor + 1) % 3]},
        "public": {
            "remaining_counts": {p: len(h) for p, h in zip(SEATS, position.hands)},
            "active_play": {"cards": list(position.target),
                            "owner": SEATS[position.owner] if position.owner is not None else None,
                            "consecutive_passes": position.passes},
            "played_counts": dict(played),
            "history_quality": "Synthetic snapshot with aggregate public card counts including the active play; no complete ordered bidding/play history is provided.",
        },
        "belief": {
            "facts": {"unseen_card_counts": dict(unseen)},
            "estimates": infer_unseen(unseen, {p: len(h) for i, (p, h) in
                                               enumerate(zip(SEATS, position.hands)) if i != actor},
                                       position.target),
            "assumptions": ["Unseen ranks are known by counting but their assignment to the two other players is unknown.",
                            "A pass does not prove a player cannot beat the current play.",
                            "Estimates assume uniformly dealt unseen card instances conditional on remaining counts; they ignore strategic past play and are not calibrated posteriors.",
                            "Seat heuristics are conditional, not mandatory rules."],
        },
        "legal_actions": actions,
    }
    if include_control_facts:
        state["belief"]["facts"]["control"] = control_facts(state)
    return state


@lru_cache(maxsize=None)
def min_plays(hand):
    if not hand:
        return 0
    results = []
    for cards in moves(hand):
        rest = list(hand)
        for c in cards:
            rest.remove(c)
        results.append(1 + min_plays(ordered(rest)))
    return min(results)
