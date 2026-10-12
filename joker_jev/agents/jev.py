"""游戏决策 JSON 边界，可注入 TypeSafeBackend 或测试后端。"""

from dataclasses import asdict
import json
from typing import Callable

from joker_jev.core.models import Decision, DecisionContext
from .base import Agent


class JEVAgent(Agent):
    def __init__(self, backend: Callable[[str], str]):
        self._backend = backend

    def decide(self, context: DecisionContext) -> Decision:
        request = {
            "task": "依据游戏规则、奖惩、可见信息与推断，选择使自身期望累计奖励最大的合法动作。推断不是真值。",
            "context": asdict(context),
            "response_schema": {
                "action_id": "必须是 observation.legal_actions 中的一个 id",
                "reason": "可选字符串，说明决策依据",
            },
        }
        response = self._backend(json.dumps(request, ensure_ascii=False, allow_nan=False))
        try:
            data = json.loads(response)
        except (ValueError, TypeError) as exc:
            raise ValueError("JEV 必须返回 JSON 对象") from exc
        if not isinstance(data, dict) or not isinstance(data.get("action_id"), str):
            raise ValueError("JEV 响应必须包含字符串 action_id")
        if not isinstance(data.get("reason", ""), str):
            raise ValueError("JEV reason 必须是字符串")
        if data["action_id"] not in {a.id for a in context.observation.legal_actions}:
            raise ValueError("JEV 返回了非法动作: " + data["action_id"])
        return Decision(data["action_id"], data.get("reason", ""))
