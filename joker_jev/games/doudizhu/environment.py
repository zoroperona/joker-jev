"""将固定小残局接入通用 CardGame 对局引擎。"""

from collections import Counter
from copy import deepcopy
from dataclasses import asdict

from joker_jev.core.game import CardGame, CardInference, Transition
from joker_jev.core.models import Action, Belief, GameRules, PlayerView, PublicEvent, RewardRule
from .strategy import DECK, SEATS, Position, infer_unseen, player_state


class EndgameInference(CardInference):
    def infer(self, observation):
        hand = observation.private["self"]["hand"]
        remaining = DECK - Counter(observation.public["played_counts"])
        unseen = remaining - Counter(hand)
        return Belief(
            {"unseen_card_counts": dict(unseen)},
            infer_unseen(unseen, {p: n for p, n in observation.public["remaining_counts"].items()
                                  if p != observation.player_id}, tuple(observation.public["active_play"]["cards"])),
            ("Uniform unseen-card instances conditional on public counts, not a behavioral posterior.",
             "Past public moves update remaining card counts; passes do not prove absence of a higher card.",
             "History starts at the supplied endgame snapshot, not at the original deal."),
        )


class EndgameGame(CardGame[Position]):
    def __init__(self, initial):
        initial.validate()
        self.initial = initial

    @property
    def rules(self):
        return GameRules(
            "doudizhu_endgame", "斗地主受限残局", "2", SEATS,
            "最大化本方团队终局奖励；任一农民先出完就是两位农民共同获胜。",
            ("当前仅支持每人最多四张、剩余普通点数至多两张的单牌/对子/王炸残局。",
             "同牌型更大或王炸可接牌；两家过牌后原领牌者自由出牌；先出完立即终局。"),
            ("自己的手牌、公开出牌、剩余张数和牌权可见；其他玩家剩余手牌不可见。",),
            (RewardRule("终局", "获胜方每名玩家", 1, "农民共享胜负"),
             RewardRule("终局", "失败方每名玩家", -1, "无中间战术加分")),
            "任何手牌变空即结束；运行步数上限不是输局。",
        )

    def initial_state(self, seed):
        return self.initial  # 固定快照；策略随机数由各 Agent 独立管理。

    def current_player(self, state):
        return SEATS[state.actor]

    def view(self, state, player_id):
        if player_id != SEATS[state.actor]:
            raise ValueError("残局接口只为当前行动者生成决策视角")
        view = player_state(state)
        return PlayerView({"self": view["self"]}, {**view["public"], "strategy_rules": view["rules"]})

    def legal_actions(self, state):
        if self.is_terminal(state):
            return ()
        return tuple(Action(**a) for a in player_state(state)["legal_actions"])

    def step(self, state, action):
        if action not in self.legal_actions(state):
            raise ValueError("残局非法动作")
        cards = tuple(action.payload["cards"])
        after = state.advance(cards)
        events = (PublicEvent("move", {"player": SEATS[state.actor], "action_id": action.id,
                                       "cards": list(cards)}),)
        rewards = {p: 0.0 for p in SEATS}
        if self.is_terminal(after):
            winner = next(i for i, h in enumerate(after.hands) if not h)
            rewards = {p: 1.0 if (i == 0) == (winner == 0) else -1.0 for i, p in enumerate(SEATS)}
            events += (PublicEvent("game_finished", {"winner": SEATS[winner], "rewards": rewards}),)
        elif not cards and state.passes == 1:
            events += (PublicEvent("free_lead", {"player": SEATS[after.actor]}),)
        return Transition(after, events, rewards)

    def is_terminal(self, state):
        return any(not h for h in state.hands)

    def create_inference(self):
        return EndgameInference()


def strategy_state(context):
    obs = context.observation
    public = deepcopy(obs.public)
    rules = public.pop("strategy_rules")
    public["history_quality"] = "Public ordered history since this endgame snapshot; earlier play is aggregate counts only."
    public["history"] = [asdict(e) for e in obs.history]
    return {"rules": rules, "self": deepcopy(obs.private["self"]), "public": public,
            "belief": asdict(context.belief), "legal_actions": [asdict(a) for a in obs.legal_actions]}
