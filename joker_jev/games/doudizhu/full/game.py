"""完整经典斗地主状态机，固定座位在叫地主后获得动态身份。"""

from collections import Counter
from dataclasses import dataclass, replace, asdict
import random

from joker_jev.core.game import CardGame, CardInference, Transition
from joker_jev.core.models import Action, Belief, GameRules, PlayerView, PublicEvent, RewardRule
from .cards import DECK, RANKS, Move, ordered, legal_moves

PLAYERS = ('p0', 'p1', 'p2')


@dataclass(frozen=True)
class State:
    hands: tuple
    bottom: tuple
    actor: int
    phase: str = 'bidding'
    bids: tuple = (-1, -1, -1)
    landlord: object = None
    bid_score: int = 0
    target: object = None
    owner: object = None
    passes: int = 0
    played: tuple = ((), (), ())
    play_counts: tuple = (0, 0, 0)
    bombs: int = 0
    winner: object = None
    spring: bool = False
    deal_number: int = 0
    seed: int = 0  # 引擎私有，仅用于全不叫时确定性重发；绝不写入玩家视角。


class FullInference(CardInference):
    def infer(self, observation):
        pub = observation.public
        hand = observation.private['hand']
        unseen = Counter(DECK) - Counter(hand) - Counter(c for cards in pub['played'].values() for c in cards)
        known = Counter()
        landlord = pub['landlord']
        if landlord is not None and landlord != observation.player_id:
            known = Counter(pub['bottom_cards']) - Counter(pub['played'][landlord])
        # 底牌是公开的地主手牌下界，其余未知牌含未揭示的底牌。
        others = {p: n for p, n in pub['remaining_counts'].items() if p != observation.player_id}
        slots = {p: n - (sum(known.values()) if p == landlord else 0) for p, n in others.items()}
        hidden_bottom = 3 if pub['phase'] == 'bidding' else 0
        pool = unseen - known
        denominator = sum(slots.values()) + hidden_bottom
        estimates = {p: {r: (known[r] if p == landlord else 0) + n * slots[p] / denominator
                         for r, n in pool.items()} for p in others} if denominator else {}
        for p in others:
            if p == landlord:
                for rank, n in known.items():
                    estimates.setdefault(p, {}).setdefault(rank, n)
        return Belief({'unseen_card_counts': dict(unseen), 'known_landlord_minimum': dict(known)},
                      {'expected_rank_counts': estimates},
                      ('Uniform remaining unknown card instances conditional on public counts and revealed bottom cards.',
                       'Passes do not prove absence of a higher card; no behavioral posterior.',))


class FullDoudizhuGame(CardGame[State]):
    @property
    def rules(self):
        return GameRules('doudizhu', '三人经典斗地主', '1', PLAYERS,
                         '叫分争取地主；出牌阶段最大化本方胜利及终局积分。任一农民出完即农民团队获胜。',
                         ('54 张牌，每家 17 张，3 张底牌；按座位叫 0/1/2/3 分，必须高于已有叫分，3 分立即确定地主。',
                          '三家都不叫则重发；地主取得并公开底牌，先出牌；农民共享胜负。',
                          '单、对、三张、三带一/对、顺子、连对、飞机及单/对翅、四带二单/二对、炸弹、王炸。',
                          '顺子至少 5、连对至少 3 对、飞机至少 2 组；连续主体不含 2 或王。',
                          '单翅可成对，但每点最多两张且不能同时带双王；翅膀不得使用主体点数；对翅必须不同点数。',
                          '四带二单允许一对，但不能带双王；四带二对必须两个不同对子。四带二不按炸弹翻倍。',
                          '同类型、同张数、同连续长度按主体点数比大小；炸弹压普通牌型，王炸最大。',
                          '自由领出不能过；两家过牌后上次出牌者自由领出；任一家出完立即结算。',
                          '炸弹/王炸各翻倍；地主胜且农民均未出牌为春天；农民胜且地主只出过一次为反春天，各再翻倍。',
                          '采用无额外加倍/抢地主选项的叫分制；底分为最高叫分。'),
                         ('仅自己手牌、公开叫分、公开底牌、出牌记录、各家剩余张数可见。',),
                         (RewardRule('终局', '地主', 2, '正负 2 × 叫分 × 倍数'),
                          RewardRule('终局', '每个农民', 1, '与地主相反的正负 1 × 叫分 × 倍数')),
                         '出完即结束。运行步数上限和接口错误不是输局。')

    def _deal(self, seed, number):
        deck = list(DECK)
        random.Random(seed + number * 1000003).shuffle(deck)
        return State(tuple(ordered(deck[i * 17:(i + 1) * 17]) for i in range(3)), ordered(deck[51:]),
                     (seed + number) % 3, deal_number=number, seed=seed)

    def initial_state(self, seed):
        return self._deal(seed, 0)

    def current_player(self, state):
        return PLAYERS[state.actor]

    def view(self, state, player_id):
        i = PLAYERS.index(player_id)
        landlord = PLAYERS[state.landlord] if state.landlord is not None else None
        role = 'unassigned' if landlord is None else ('landlord' if i == state.landlord else 'farmer')
        teammate = next((p for j, p in enumerate(PLAYERS) if j != i and j != state.landlord), None) if role == 'farmer' else None
        return PlayerView({'hand': list(state.hands[i]), 'role': role, 'teammate': teammate},
                          {'phase': state.phase, 'actor': PLAYERS[state.actor], 'landlord': landlord,
                           'next_player': PLAYERS[(i + 1) % 3], 'bids': dict(zip(PLAYERS, state.bids)),
                           'bid_score': state.bid_score, 'deal_number': state.deal_number,
                           'bottom_cards': list(state.bottom) if landlord else [],
                           'remaining_counts': {p: len(h) for p, h in zip(PLAYERS, state.hands)},
                           'target': asdict(state.target) if state.target else None,
                           'owner': PLAYERS[state.owner] if state.owner is not None else None,
                           'passes': state.passes, 'played': {p: list(c) for p, c in zip(PLAYERS, state.played)},
                           'play_counts': dict(zip(PLAYERS, state.play_counts)), 'bombs': state.bombs,
                           'multiplier': 2 ** (state.bombs + int(state.spring))})

    def legal_actions(self, state):
        if self.is_terminal(state):
            return ()
        if state.phase == 'bidding':
            return tuple(Action('bid:%d' % n, '不叫' if n == 0 else '叫 %d 分' % n, {'bid': n})
                         for n in (0, 1, 2, 3) if n == 0 or n > state.bid_score)
        actions = tuple(Action(m.id, m.kind + ' ' + ' '.join(m.cards), asdict(m))
                        for m in legal_moves(state.hands[state.actor], state.target))
        return actions + ((Action('pass', '过牌', {'cards': (), 'kind': 'pass'}),) if state.target else ())

    def step(self, state, action):
        if action not in self.legal_actions(state):
            raise ValueError('非法斗地主动作')
        rewards = {p: 0.0 for p in PLAYERS}
        actor = state.actor
        if state.phase == 'bidding':
            bid = action.payload['bid']
            bids = list(state.bids)
            bids[actor] = bid
            score = max(state.bid_score, bid)
            landlord = bids.index(score) if score else None
            events = [PublicEvent('bid', {'player': PLAYERS[actor], 'bid': bid, 'deal_number': state.deal_number})]
            if bid == 3 or all(n >= 0 for n in bids):
                if score == 0:
                    after = self._deal(state.seed, state.deal_number + 1)
                    events.append(PublicEvent('redeal', {'deal_number': after.deal_number, 'first_bidder': PLAYERS[after.actor]}))
                else:
                    hands = list(state.hands)
                    hands[landlord] = ordered(hands[landlord] + state.bottom)
                    after = replace(state, hands=tuple(hands), actor=landlord, landlord=landlord,
                                    bids=tuple(bids), bid_score=score, phase='playing')
                    events.append(PublicEvent('landlord_selected', {'landlord': PLAYERS[landlord],
                                                                   'bottom_cards': list(state.bottom), 'bid_score': score}))
            else:
                # 叫分最高者尚未最终成为地主，私有底牌仍不公开。
                after = replace(state, bids=tuple(bids), bid_score=score, actor=(actor + 1) % 3)
                # 最高叫分人的身份可从公开 bids 推导，无须泄露底牌。
            return Transition(after, tuple(events), rewards)
        cards = tuple(action.payload['cards'])
        events = [PublicEvent('move', {'player': PLAYERS[actor], 'action_id': action.id, 'cards': list(cards),
                                     'kind': action.payload['kind']})]
        if not cards:
            if state.passes == 1:
                after = replace(state, actor=state.owner, target=None, owner=None, passes=0)
                events.append(PublicEvent('free_lead', {'player': PLAYERS[after.actor]}))
            else:
                after = replace(state, actor=(actor + 1) % 3, passes=1)
            return Transition(after, tuple(events), rewards)
        hands = list(state.hands)
        hand = list(hands[actor])
        for card in cards:
            hand.remove(card)
        hands[actor] = tuple(hand)
        played = list(state.played)
        played[actor] += cards
        counts = list(state.play_counts)
        counts[actor] += 1
        move = Move(cards, action.payload['kind'], action.payload['main'], action.payload['chain'])
        after = replace(state, hands=tuple(hands), target=move, owner=actor, passes=0,
                        actor=(actor + 1) % 3, played=tuple(played), play_counts=tuple(counts),
                        bombs=state.bombs + int(move.kind in ('bomb', 'rocket')))
        if not hand:
            landlord_won = actor == state.landlord
            spring = (all(counts[i] == 0 for i in range(3) if i != state.landlord) if landlord_won
                      else counts[state.landlord] == 1)
            after = replace(after, phase='finished', winner=actor, spring=spring)
            unit = state.bid_score * 2 ** (after.bombs + int(spring))
            sign = 1 if landlord_won else -1
            rewards = {p: float(sign * unit * (2 if i == state.landlord else -1)) for i, p in enumerate(PLAYERS)}
            events.append(PublicEvent('game_finished', {'winner': PLAYERS[actor], 'landlord': PLAYERS[state.landlord],
                                                       'spring': spring, 'multiplier': 2 ** (after.bombs + int(spring)),
                                                       'rewards': rewards}))
        return Transition(after, tuple(events), rewards)

    def is_terminal(self, state):
        return state.phase == 'finished'

    def create_inference(self):
        return FullInference()
