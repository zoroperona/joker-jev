"""完整残局运行、逐步重算、逐次 API 计量。"""

from copy import deepcopy
from dataclasses import asdict, is_dataclass
import json
from pathlib import Path
import random
import time

from joker_jev.agents.base import Agent
from joker_jev.agents.typesafe import TypeSafeError
from joker_jev.core.engine import TurnLimitError, play
from joker_jev.core.models import Decision
from .environment import EndgameGame, strategy_state
from .rollout import choose_hybrid, choose_simulation, policy_action, score_actions
from .strategy import SEATS, control_facts
from .tactics import decide

ARMS = ("current_jev", "simulation", "simulation_jev")


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                               default=lambda v: asdict(v) if is_dataclass(v) else str(v)) + "\n", encoding="utf-8")
    temp.replace(path)


class MeteredBackend:
    def __init__(self, backend, ledger, save):
        self.backend, self.ledger, self.save = backend, ledger, save

    def evaluate(self, state, questions):
        entry = {"questions": list(questions), "status": "pending"}
        self.ledger.append(entry)
        self.save()
        start = time.perf_counter()
        try:
            response = self.backend.evaluate(state, questions)
            entry.update(status="completed", model=response.get("model"), usage=response.get("usage", {}))
            return response
        except TypeSafeError as exc:
            entry.update(status="api_error", error=str(exc), usage_unknown=True)
            raise
        finally:
            entry["seconds"] = time.perf_counter() - start
            self.save()


class ReplanningAgent(Agent):
    def __init__(self, mode, trace, save, seed=0, backend=None):
        self.mode, self.trace, self.save, self.backend = mode, trace, save, backend
        self.rng = random.Random(seed)

    def decide(self, context):
        state = strategy_state(context)
        record = {"turn": context.observation.turn, "player": context.observation.player_id,
                  "policy": self.mode, "visible_state": deepcopy(state), "status": "deciding"}
        self.trace.append(record)
        self.save()
        if len(state["legal_actions"]) == 1:
            choice = {"action_id": state["legal_actions"][0]["id"], "forced": True, "calls": []}
        elif self.mode == "current_jev":
            choice = decide(state, self.backend)
        elif self.mode in ("simulation", "simulation_jev"):
            analysis = score_actions(state)  # 每轮由最新视角重新计算，不复用首步动作。
            record["planning_analysis"] = analysis
            self.save()
            choice = choose_simulation(analysis) if self.mode == "simulation" else choose_hybrid(state, analysis, self.backend)
        else:
            state["belief"]["facts"]["control"] = control_facts(state)
            record["visible_state"] = deepcopy(state)
            choice = {"action_id": policy_action(state, self.mode, self.rng), "calls": []}
        record.update(decision=choice, status="selected")
        self.save()
        return Decision(choice["action_id"])


def run_episode(initial, arm, focal_seat, farmer_style="cooperative", seed=0,
                backend=None, max_turns=36, output=None, landlord_style="pressure"):
    styles = ("cooperative", "greedy", "random", "pressure", "conservative")
    if arm not in ARMS or focal_seat not in SEATS or farmer_style not in styles or landlord_style not in styles:
        raise ValueError("无效的策略、目标座位或农民搭档风格")
    if arm != "simulation" and backend is None:
        raise ValueError("JEV 策略需要后端")
    if max_turns <= 0:
        raise ValueError("max_turns 必须为正")
    if output and Path(output).exists():
        raise ValueError("对局记录已存在")
    # 非目标地主和农民采用指定风格；仅目标座位使用被测策略。
    modes = {p: (arm if p == focal_seat else landlord_style if p == "landlord" else farmer_style) for p in SEATS}
    result = {"arm": arm, "focal_seat": focal_seat, "farmer_style": farmer_style, "seed": seed,
              "landlord_style": landlord_style, "policy_by_seat": modes, "status": "running", "trace": [], "api_ledger": [],
              "team_reward": None, "rewards": None}
    def save():
        if output:
            write_json(output, result)
    metered = MeteredBackend(backend, result["api_ledger"], save) if backend else None
    agents = {p: ReplanningAgent(modes[p], result["trace"], save, seed + i, metered)
              for i, p in enumerate(SEATS)}
    def on_step(step):
        record = result["trace"][-1]
        record.update(status="applied", decision_seconds=step["decision_seconds"],
                      public_events=[asdict(e) for e in step["events"]],
                      rewards=step["rewards"], cumulative_rewards=step["cumulative_rewards"])
        save()
    start = time.perf_counter()
    save()
    try:
        episode = play(EndgameGame(initial), agents, seed=seed, max_turns=max_turns, on_step=on_step)
        result.update(status="completed", turns=episode.turns, rewards=episode.rewards,
                      team_reward=episode.rewards[focal_seat],
                      public_history=[asdict(e) for e in episode.history])
    except TypeSafeError as exc:
        result.update(status="api_error", error=str(exc))
    except TurnLimitError as exc:
        result.update(status="turn_limit", error=str(exc))
    except Exception as exc:
        result.update(status="implementation_error", error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        result["elapsed_seconds"] = time.perf_counter() - start
        result["applied_turns"] = sum(t["status"] == "applied" for t in result["trace"])
        save()
    return result
