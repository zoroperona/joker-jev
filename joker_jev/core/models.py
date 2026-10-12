from dataclasses import dataclass, field
from typing import Any, Dict, Tuple


@dataclass(frozen=True)
class RewardRule:
    trigger: str
    recipient: str
    value: float
    description: str


@dataclass(frozen=True)
class GameRules:
    game_id: str
    name: str
    version: str
    players: Tuple[str, ...]
    objective: str
    rules: Tuple[str, ...]
    information: Tuple[str, ...]
    rewards: Tuple[RewardRule, ...]
    termination: str


@dataclass(frozen=True)
class Action:
    id: str
    label: str
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PublicEvent:
    """只允许包含全体玩家都能看到的信息。"""

    kind: str
    data: Dict[str, Any]


@dataclass(frozen=True)
class PlayerView:
    private: Dict[str, Any]
    public: Dict[str, Any]


@dataclass(frozen=True)
class Observation:
    game_id: str
    player_id: str
    turn: int
    private: Dict[str, Any]
    public: Dict[str, Any]
    legal_actions: Tuple[Action, ...]
    history: Tuple[PublicEvent, ...]


@dataclass(frozen=True)
class Belief:
    """推断而非真值；概率、候选牌和统计由具体游戏定义。"""

    facts: Dict[str, Any]
    estimates: Dict[str, Any]
    assumptions: Tuple[str, ...]


@dataclass(frozen=True)
class DecisionContext:
    rules: GameRules
    observation: Observation
    belief: Belief
    cumulative_reward: float
    protocol_version: str = "1"


@dataclass(frozen=True)
class Decision:
    action_id: str
    reason: str = ""
