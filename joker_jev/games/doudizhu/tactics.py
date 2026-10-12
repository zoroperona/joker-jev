"""两阶段战术判断；只接受已隔离的玩家状态。"""

from copy import deepcopy

from joker_jev.agents.typesafe import TypeSafeError

QUESTIONS = {
    "must_block": {"type": "noul", "instructions":
                   "Does the visible state indicate an urgent need to stop the opposing team from emptying a hand on its next opportunity? Treat hidden-card estimates as uncertain."},
    "yield_control": {"type": "noul", "instructions":
                      "Should this player pass to preserve a farmer teammate's active lead? Answer no for the landlord or if no teammate owns the active play. Account for an enemy intervening."},
    "feed_teammate": {"type": "noul", "instructions":
                       "When leading freely, is playing a small single to let the next farmer teammate finish a useful plan? Answer no if not applicable. Use the actual turn order."},
    "pair_pressure": {"type": "noul", "instructions":
                      "Can leading a pair keep a one-card enemy from responding while preserving this player's route to finish? Answer no if not applicable."},
}

ACTION_INSTRUCTIONS = "Which legal action best serves this player's team winning objective? Use turn order, visible information, computed action features and uncertain tactical assessments. Either farmer finishing is equally a farmer victory. Do not treat a seat heuristic as mandatory."


def validate_choice(answer, ids):
    try:
        probabilities = answer["probabilities"]
        if answer["type"] != "choice" or answer["choice"] not in ids or set(probabilities) != set(ids):
            raise ValueError()
        for value in [answer["confidence"], *probabilities.values()]:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
                raise ValueError()
        if abs(sum(probabilities.values()) - 1) > 0.01:
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise TypeSafeError("战术选择返回无效 Choice") from None


def decide(state, backend):
    """不接收 Scenario 或 Position，防止评测标签和完整底牌进入请求。"""
    actions = state["legal_actions"]
    if len(actions) == 1:
        return {"action_id": actions[0]["id"], "tactics": {}, "calls": [], "forced": True}
    first = backend.evaluate(deepcopy(state), deepcopy(QUESTIONS))
    tactics = {}
    for key in QUESTIONS:
        try:
            answer = first["answers"][key]
            value = answer["noul"]
            if answer["type"] != "noul" or isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise TypeSafeError("战术判断返回无效 Noul") from None
        tactics[key] = value
    second_state = deepcopy(state)
    second_state["tactical_assessments"] = {
        "estimates": tactics,
        "meaning": "Independent uncertain model judgments, not rewards or facts. Prefer immediate team victory over intermediate tactics.",
    }
    criteria = {a["id"]: {"label": a["label"], **a["payload"]} for a in actions}
    if len(criteria) > 255:
        raise ValueError("Choice 超过 255 个动作")
    second = backend.evaluate(second_state, {"action": {
        "type": "choice",
        "instructions": ACTION_INSTRUCTIONS,
        "criteria": criteria,
    }})
    answer = second["answers"]["action"]
    validate_choice(answer, criteria)
    return {"action_id": answer["choice"], "tactics": tactics,
            "confidence": answer["confidence"], "probabilities": answer["probabilities"],
            "calls": [{"model": r.get("model"), "usage": r.get("usage", {})} for r in (first, second)],
            "forced": False}
