from copy import deepcopy
from dataclasses import dataclass
import math
import time
from typing import Dict, Mapping, Tuple

from joker_jev.agents.base import Agent
from .game import CardGame
from .models import Decision, DecisionContext, Observation, PublicEvent


@dataclass(frozen=True)
class EpisodeResult:
    game_id: str
    turns: int
    rewards: Dict[str, float]
    history: Tuple[PublicEvent, ...]


class TurnLimitError(RuntimeError):
    """运行上限，不是游戏规则中的输局或平局。"""


def play(game: CardGame, agents: Mapping[str, Agent], seed: int = 0,
         max_turns: int = 1000, on_step=None) -> EpisodeResult:
    """驱动任何实现 CardGame 的轮流行动游戏；非法决策直接失败。"""
    rules = game.rules
    players = rules.players
    if not players or len(set(players)) != len(players):
        raise ValueError("玩家列表不能为空或重复")
    if set(agents) != set(players):
        raise ValueError("必须为每个玩家提供一个 Agent")
    if max_turns <= 0:
        raise ValueError("max_turns 必须为正数")

    state = game.initial_state(seed)
    inference = {player: game.create_inference() for player in players}
    totals = {player: 0.0 for player in players}
    history = ()
    turn = 0
    while not game.is_terminal(state):
        if turn >= max_turns:
            raise TurnLimitError("对局超过 max_turns，游戏可能未正确结束")
        player = game.current_player(state)
        if player not in agents:
            raise ValueError("游戏返回未知玩家")
        actions = game.legal_actions(state)
        by_id = {action.id: action for action in actions}
        if not actions or len(by_id) != len(actions):
            raise ValueError("非终局必须提供非空且 id 唯一的合法动作")
        view = game.view(state, player)
        observation = deepcopy(Observation(
            rules.game_id, player, turn, view.private, view.public, actions, history,
        ))
        belief = inference[player].infer(deepcopy(observation))
        context = deepcopy(DecisionContext(rules, observation, belief, totals[player]))
        started = time.perf_counter()
        decision = agents[player].decide(context)
        decision_seconds = time.perf_counter() - started
        if not isinstance(decision, Decision) or decision.action_id not in by_id:
            raise ValueError("Agent 必须返回合法的 Decision")
        # 使用游戏给出的原始动作，不能信任 Agent 修改后的 payload。
        transition = game.step(state, by_id[decision.action_id])
        if set(transition.rewards) != set(players):
            raise ValueError("每步奖励必须覆盖全部玩家（无奖励填 0）")
        for recipient, reward in transition.rewards.items():
            if isinstance(reward, bool) or not isinstance(reward, (int, float)) or not math.isfinite(reward):
                raise ValueError("奖励必须是有限数值")
            totals[recipient] += reward
        state = transition.state
        history += deepcopy(transition.events)
        if on_step is not None:
            on_step(deepcopy({"turn": turn, "player_id": player, "decision": decision,
                              "decision_seconds": decision_seconds, "events": transition.events,
                              "rewards": transition.rewards, "cumulative_rewards": totals}))
        turn += 1
    return EpisodeResult(rules.game_id, turn, totals, history)
