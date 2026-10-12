from abc import ABC, abstractmethod
import random

from joker_jev.core.models import Decision, DecisionContext


class Agent(ABC):
    @abstractmethod
    def decide(self, context: DecisionContext) -> Decision:
        raise NotImplementedError


class RandomAgent(Agent):
    """独立随机源，避免与洗牌随机数共享导致底牌泄露。"""

    def __init__(self, seed: int = 0):
        self._random = random.Random(seed)

    def decide(self, context: DecisionContext) -> Decision:
        action = self._random.choice(context.observation.legal_actions)
        return Decision(action.id, "随机基线")
