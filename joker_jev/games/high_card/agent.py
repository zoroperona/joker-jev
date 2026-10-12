from joker_jev.agents.base import Agent
from joker_jev.core.models import Decision, DecisionContext


class HighCardHeuristicAgent(Agent):
    """可解释基线，用于跑通环境，不代表 JEV 或最优策略。"""

    def decide(self, context: DecisionContext) -> Decision:
        observation = context.observation
        actions = sorted(observation.legal_actions, key=lambda a: a.payload["card"])
        trick = observation.public["trick"]
        if trick:
            beating = [a for a in actions if a.payload["card"] > trick[0]["card"]]
            action = beating[0] if beating else actions[0]
            return Decision(action.id, "能赢则用最小可赢牌，否则放弃最小牌")
        return Decision(actions[-1].id, "先手出最大牌争取本轮奖励")
