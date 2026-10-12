"""枚举公开信息兼容的牌分配，以玩家视角策略模拟后续；不调用全知求解器。"""

from collections import Counter
from copy import deepcopy
from itertools import combinations
import random

from .strategy import Position, RANKS, SEATS, action_id, ordered, player_state
from .tactics import validate_choice

PLANNING_POLICIES = ("cooperative", "greedy")
EVALUATION_POLICIES = ("random", "pressure")
HYBRID_INSTRUCTIONS = (
    "Choose the legal action that best serves this player's team reward. Compare the supplied "
    "immediate consequences and rollout estimates. The estimates depend on uniform hidden-card "
    "assignments and simple continuation policies, are not optimal values or real win probabilities. "
    "Either farmer finishing is equally a farmer victory. You may disagree with the simulation ranking."
)


def compatible_worlds(state):
    """输入仅含玩家视角；相同点数不同实体分配合并，但保留组合权重。"""
    actor = SEATS.index(state["self"]["seat"])
    others = [i for i in range(3) if i != actor]
    pool = ordered(Counter(state["belief"]["facts"]["unseen_card_counts"]).elements())
    counts = state["public"]["remaining_counts"]
    if len(pool) != sum(counts[SEATS[i]] for i in others):
        raise ValueError("未知牌数量与公开剩余牌数不符")
    active = state["public"]["active_play"]
    weighted = Counter()
    for indices in combinations(range(len(pool)), counts[SEATS[others[0]]]):
        indices = set(indices)
        hands = [(), (), ()]
        hands[actor] = ordered(state["self"]["hand"])
        hands[others[0]] = tuple(c for i, c in enumerate(pool) if i in indices)
        hands[others[1]] = tuple(c for i, c in enumerate(pool) if i not in indices)
        pos = Position(tuple(hands), actor, tuple(active["cards"]),
                       SEATS.index(active["owner"]) if active["owner"] else None,
                       active["consecutive_passes"])
        pos.validate()
        weighted[pos] += 1
    total = sum(weighted.values())
    if not total:
        raise ValueError("没有与公开信息一致的牌分配")
    return [(pos, weight / total) for pos, weight in weighted.items()]


def policy_action(state, policy, rng):
    """只接受玩家可见状态。策略是比较基线，不是最优解或硬规则。"""
    actions = state["legal_actions"]
    if policy == "random":
        return rng.choice(actions)["id"]
    if policy not in (*PLANNING_POLICIES, "pressure", "conservative"):
        raise ValueError("未知续局策略")
    finishing = [a for a in actions if a["payload"]["finishes_own_hand"]]
    if finishing:
        return finishing[0]["id"]
    plays = [a for a in actions if a["payload"]["cards"]]
    if not plays:
        return "pass"
    active = state["public"]["active_play"]
    if policy == "conservative":
        # 保留对子和大牌；队友掌握牌权时让牌。仅使用当前视角。
        if active["cards"] and active["owner"] == state["self"]["teammate"]:
            return "pass"
        return min(plays, key=lambda a: (a["payload"]["breaks_pair"],
                   RANKS.index(a["payload"]["cards"][-1])))["id"]
    if policy == "cooperative":
        facts = state["belief"]["facts"]["control"]
        if (active["cards"] and facts["active_owner_is_teammate"]
                and not facts["opponent_can_possibly_finish_on_current_play_after_self_pass"]):
            return "pass"
        if not active["cards"]:
            teammate = state["self"]["teammate"]
            singles = [a for a in plays if a["payload"]["kind"] == "single"]
            if (teammate == state["self"]["next_seat"]
                    and state["public"]["remaining_counts"].get(teammate) == 1 and singles):
                return singles[0]["id"]
            teams = state["rules"]["team"]
            team = teams[state["self"]["seat"]]
            pairs = [a for a in plays if a["payload"]["kind"] == "pair"]
            if pairs and any(n == 1 and teams[p] != team for p, n in state["public"]["remaining_counts"].items()):
                return pairs[0]["id"]
    if policy == "pressure" and active["cards"]:
        return max(plays, key=lambda a: RANKS.index(a["payload"]["cards"][-1]))["id"]
    if policy == "pressure":
        return plays[0]["id"]
    return min(plays, key=lambda a: (
        a["payload"]["minimum_uncontested_plays"],
        a["payload"]["breaks_pair"], RANKS.index(a["payload"]["cards"][-1]),
    ))["id"]


def team_reward(position, root_seat):
    winner = next((i for i, hand in enumerate(position.hands) if not hand), None)
    if winner is None:
        return None
    return 1 if (winner == 0) == (root_seat == 0) else -1


def simulate(position, first_action, policy, seed=0, max_turns=36):
    if max_turns <= 0:
        raise ValueError("max_turns 必须为正")
    root = position.actor
    first = next((a for a in player_state(position)["legal_actions"] if a["id"] == first_action), None)
    if first is None:
        raise ValueError("模拟动作不合法")
    current = position.advance(tuple(first["payload"]["cards"]))
    rng = random.Random(seed)
    turns = 1
    while team_reward(current, root) is None and turns < max_turns:
        view = player_state(current, include_control_facts=True)
        chosen = policy_action(view, policy, rng)
        action = next(a for a in view["legal_actions"] if a["id"] == chosen)
        current = current.advance(tuple(action["payload"]["cards"]))
        turns += 1
    return {"reward": team_reward(current, root), "turns": turns}


def score_actions(state, policies=PLANNING_POLICIES, seeds=(0,), max_turns=36):
    if not policies or not seeds or max_turns <= 0:
        raise ValueError("策略、随机种子不能为空，模拟步数须为正")
    worlds = compatible_worlds(state)
    actions = []
    for action in state["legal_actions"]:
        profiles = {}
        for policy in policies:
            wins = losses = truncated = mean_turns = 0.0
            for world, weight in worlds:
                for seed in seeds:
                    result = simulate(world, action["id"], policy, seed, max_turns)
                    mass = weight / len(seeds)
                    wins += mass * (result["reward"] == 1)
                    losses += mass * (result["reward"] == -1)
                    truncated += mass * (result["reward"] is None)
                    mean_turns += mass * result["turns"]
            profiles[policy] = {
                "team_win_mass": wins, "team_loss_mass": losses, "truncated_mass": truncated,
                "expected_team_reward": wins - losses if truncated < 1e-12 else None,
                "reward_lower_bound": wins - losses - truncated,
                "reward_upper_bound": wins - losses + truncated,
                "mean_turns": mean_turns,
            }
        payload = action["payload"]
        active = state["public"]["active_play"]
        passing = not payload["cards"]
        ends_trick = passing and active["consecutive_passes"] == 1
        actions.append({
            "action_id": action["id"],
            "immediate": {
                "finishes_team_game": payload["finishes_own_hand"],
                "remaining_hand": payload["remaining_hand"],
                "minimum_uncontested_plays": payload["minimum_uncontested_plays"],
                "breaks_pair": payload["breaks_pair"],
                "next_seat": None if payload["finishes_own_hand"] else (
                    active["owner"] if ends_trick else state["self"]["next_seat"]),
                "active_owner_after_action": active["owner"] if passing else state["self"]["seat"],
                "returns_free_lead_to_owner": ends_trick,
            },
            "by_continuation_policy": profiles,
            "worst_policy_reward_lower_bound": min(p["reward_lower_bound"] for p in profiles.values()),
            "mean_policy_reward_lower_bound": sum(p["reward_lower_bound"] for p in profiles.values()) / len(profiles),
        })
    return {
        "unique_hidden_assignments": len(worlds), "policies": list(policies), "seeds": list(seeds),
        "max_turns": max_turns, "simulated_trajectories": len(worlds) * len(actions) * len(policies) * len(seeds),
        "assumptions": ["Uniform unseen card instances conditional on public counts; no behavioral posterior.",
                        "All continuation players see only their own hands and public information.",
                        "Policy-dependent rollout values, not optimal values or calibrated real-world win probabilities.",
                        "Truncated trajectories retain reward interval [-1,1]; they are not counted as losses."],
        "actions": actions,
    }


def choose_simulation(analysis):
    # 平局时优先立即终局，最后用输入顺序稳定破同分；不使用人工建议。
    selected = max(analysis["actions"], key=lambda a: (
        a["worst_policy_reward_lower_bound"], a["mean_policy_reward_lower_bound"],
        a["immediate"]["finishes_team_game"],
    ))
    return {"action_id": selected["action_id"], "calls": [],
            "selection": "max worst-policy lower bound, then mean lower bound, then immediate finish"}


def choose_hybrid(state, analysis, backend):
    if len(state["legal_actions"]) == 1:
        return {"action_id": state["legal_actions"][0]["id"], "calls": [], "forced": True}
    enriched = deepcopy(state)
    enriched["candidate_consequences"] = deepcopy(analysis)
    criteria = {a["id"]: {"label": a["label"], **a["payload"]} for a in state["legal_actions"]}
    response = backend.evaluate(enriched, {"action": {
        "type": "choice", "instructions": HYBRID_INSTRUCTIONS, "criteria": criteria,
    }})
    answer = response["answers"]["action"]
    validate_choice(answer, criteria)
    return {"action_id": answer["choice"], "probabilities": answer["probabilities"],
            "confidence": answer["confidence"], "forced": False,
            "calls": [{"model": response.get("model"), "usage": response.get("usage", {})}]}
