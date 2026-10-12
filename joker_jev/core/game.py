from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Generic, Tuple, TypeVar

from .models import Action, Belief, GameRules, Observation, PlayerView, PublicEvent

State = TypeVar("State")


class CardInference(ABC):
    @abstractmethod
    def infer(self, observation: Observation) -> Belief:
        """只能使用玩家视角和公开历史，禁止读取真实游戏状态。"""
        raise NotImplementedError


@dataclass(frozen=True)
class Transition(Generic[State]):
    state: State
    events: Tuple[PublicEvent, ...]
    rewards: Dict[str, float]


class CardGame(ABC, Generic[State]):
    @property
    @abstractmethod
    def rules(self) -> GameRules:
        raise NotImplementedError

    @abstractmethod
    def initial_state(self, seed: int) -> State:
        raise NotImplementedError

    @abstractmethod
    def current_player(self, state: State) -> str:
        raise NotImplementedError

    @abstractmethod
    def view(self, state: State, player_id: str) -> PlayerView:
        """仅返回该玩家可见的状态，不包含随机种子或对手底牌。"""
        raise NotImplementedError

    @abstractmethod
    def legal_actions(self, state: State) -> Tuple[Action, ...]:
        raise NotImplementedError

    @abstractmethod
    def step(self, state: State, action: Action) -> Transition[State]:
        """产生新状态及本步增量奖励；终局奖励也在终止的这一步发放。"""
        raise NotImplementedError

    @abstractmethod
    def is_terminal(self, state: State) -> bool:
        raise NotImplementedError

    @abstractmethod
    def create_inference(self) -> CardInference:
        raise NotImplementedError
