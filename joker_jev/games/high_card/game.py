from dataclasses import dataclass
import random
from typing import Tuple

from joker_jev.core.game import CardGame, Transition
from joker_jev.core.models import Action, GameRules, PlayerView, PublicEvent, RewardRule
from .inference import HighCardInference

PLAYERS = ("p0", "p1")
DECK = tuple(range(1, 9))
HAND_SIZE = 3


@dataclass(frozen=True)
class HighCardState:
    hands: Tuple[Tuple[int, ...], Tuple[int, ...]]
    current: str
    trick: Tuple[Tuple[str, int], ...] = ()
    scores: Tuple[int, int] = (0, 0)
    completed_tricks: int = 0


class HighCardGame(CardGame[HighCardState]):
    @property
    def rules(self) -> GameRules:
        return GameRules(
            game_id="high_card", name="双人三轮比牌", version="1.0", players=PLAYERS,
            objective="最大化三轮累计奖励，即赢得尽可能多的轮次。",
            rules=(
                "牌堆为 1 至 8 各一张，均匀洗牌后每人发 3 张，剩余 2 张不使用且不公开。",
                "p0 首轮先手，每轮双方各出一张；后手能看到先手出的牌。",
                "较大的牌赢得本轮，赢家下一轮先手；已经打出的牌不能再使用。",
                "一共三轮；单次出牌就是一个动作。",
            ),
            information=("可见自己的手牌、所有已出牌、双方剩余牌数和比分。", "对手手牌和未发出的牌不可见。"),
            rewards=(
                RewardRule("轮次结束", "本轮赢家", 1.0, "赢一轮获得 1 分奖励"),
                RewardRule("轮次结束", "本轮输家", -1.0, "输一轮扣 1 分奖励"),
                RewardRule("只有先手出牌", "所有玩家", 0.0, "尚未结算"),
            ),
            termination="三轮完成即终局，无额外终局奖励；累计奖励较高者获胜。",
        )

    def initial_state(self, seed: int) -> HighCardState:
        deck = list(DECK)
        random.Random(seed).shuffle(deck)
        return HighCardState((tuple(sorted(deck[:3])), tuple(sorted(deck[3:6]))), "p0")

    def current_player(self, state: HighCardState) -> str:
        return state.current

    def view(self, state: HighCardState, player_id: str) -> PlayerView:
        index = PLAYERS.index(player_id)
        return PlayerView(
            private={"hand": list(state.hands[index])},
            public={
                "deck": list(DECK), "current_player": state.current,
                "hand_counts": {p: len(state.hands[i]) for i, p in enumerate(PLAYERS)},
                "scores": dict(zip(PLAYERS, state.scores)),
                "trick": [{"player": p, "card": c} for p, c in state.trick],
                "completed_tricks": state.completed_tricks,
            },
        )

    def legal_actions(self, state: HighCardState) -> Tuple[Action, ...]:
        if self.is_terminal(state):
            return ()
        return tuple(Action("play:" + str(c), "出 " + str(c), {"card": c})
                     for c in state.hands[PLAYERS.index(state.current)])

    def step(self, state: HighCardState, action: Action) -> Transition[HighCardState]:
        if action not in self.legal_actions(state):
            raise ValueError("非法出牌")
        card = action.payload["card"]
        actor = state.current
        hands = tuple(tuple(c for c in hand if not (i == PLAYERS.index(actor) and c == card))
                      for i, hand in enumerate(state.hands))
        trick = state.trick + ((actor, card),)
        events = (PublicEvent("card_played", {"player": actor, "card": card}),)
        rewards = {p: 0.0 for p in PLAYERS}
        if len(trick) == 1:
            next_player = PLAYERS[1 - PLAYERS.index(actor)]
            next_state = HighCardState(hands, next_player, trick, state.scores, state.completed_tricks)
        else:
            winner = max(trick, key=lambda item: item[1])[0]
            scores = tuple(score + int(p == winner) for p, score in zip(PLAYERS, state.scores))
            rewards = {p: 1.0 if p == winner else -1.0 for p in PLAYERS}
            events += (PublicEvent("trick_completed", {"winner": winner, "scores": dict(zip(PLAYERS, scores))}),)
            next_state = HighCardState(hands, winner, (), scores, state.completed_tricks + 1)
        return Transition(next_state, events, rewards)

    def is_terminal(self, state: HighCardState) -> bool:
        return state.completed_tricks == HAND_SIZE

    def create_inference(self) -> HighCardInference:
        return HighCardInference()
