"""三种首步决策的对照；策略收益与实现错误分开统计。"""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import time

from joker_jev.agents.typesafe import TypeSafeBackend, TypeSafeError
from .rollout import (EVALUATION_POLICIES, HYBRID_INSTRUCTIONS, choose_hybrid,
                      choose_simulation, score_actions)
from .scenarios import SCENARIOS, COOPERATION_SCENARIOS
from .strategy import oracle_actions, player_state
from .tactics import ACTION_INSTRUCTIONS, QUESTIONS, decide


def summarize(trials):
    result = {}
    for arm in dict.fromkeys(t["arm"] for t in trials):
        attempts = [t for t in trials if t["arm"] == arm]
        done = [t for t in attempts if "outcomes" in t]
        usage = Counter()
        for trial in done:
            for call in trial["decision"].get("calls", []):
                usage.update({k: v for k, v in call.get("usage", {}).items() if isinstance(v, (int, float))})
        def mean(key):
            return sum(t["outcomes"][key] for t in done) / len(done) if done else None
        per_case = {}
        for trial in done:
            per_case.setdefault(trial["case_id"], []).append(trial["decision"]["action_id"])
        result[arm] = {
            "attempted": len(attempts), "completed": len(done), "execution_errors": len(attempts) - len(done),
            "mean_evaluation_team_reward_lower_bound": mean("reward_lower_bound"),
            "mean_evaluation_team_reward_upper_bound": mean("reward_upper_bound"),
            "mean_evaluation_team_win_mass": mean("team_win_mass"),
            "mean_evaluation_truncated_mass": mean("truncated_mass"),
            "mean_decision_seconds": sum(t["decision_seconds"] for t in done) / len(done) if done else None,
            "api_calls": sum(len(t["decision"].get("calls", [])) for t in done), "usage": dict(usage),
            "human_reference_agreements": sum(t["diagnostics"]["human_reference_agreement"] for t in done),
            "repeated_case_action_consistency": {
                c: max(Counter(actions).values()) / len(actions) for c, actions in per_case.items() if len(actions) > 1},
        }
    return result


def paired_summary(trials, arms):
    groups = {}
    for trial in trials:
        if "outcomes" in trial:
            groups.setdefault((trial["case_id"], trial["repetition"]), {})[trial["arm"]] = trial
    complete = [g for g in groups.values() if set(g) == set(arms)]
    return {"complete_case_repetition_groups": len(complete),
            "summary": summarize([g[arm] for g in complete for arm in arms])}


def benchmark(backend=None, repeats=1, seed=2026, output=None, cases=None, progress=None):
    if repeats <= 0:
        raise ValueError("repeats 必须为正")
    path = Path(output) if output else None
    if path and path.exists():
        raise ValueError("报告已存在，请指定新路径")
    cases = tuple(cases) if cases is not None else tuple(
        {c.id: c for c in (*SCENARIOS, *COOPERATION_SCENARIOS)}.values())
    arms = ("current_jev", "simulation", "simulation_jev") if backend else ("simulation",)
    report = {
        "started_at": datetime.now(timezone.utc).isoformat(), "status": "running",
        "protocol": "doudizhu_root_action_v1", "requested_model": backend.model if backend else None,
        "seed": seed, "repeats": repeats, "arms": arms,
        "questions": QUESTIONS, "current_action_instructions": ACTION_INSTRUCTIONS,
        "hybrid_instructions": HYBRID_INSTRUCTIONS,
        "limitations": ["Only the initial decision differs; all subsequent players use shared evaluation policies.",
                         "Planning uses cooperative/greedy continuation; evaluation uses random/pressure instead.",
                         "Hidden assignments are enumerated with uniform card-instance weights, not a calibrated behavioral posterior.",
                         "Evaluation reward is specific to these synthetic snapshots and policies, not full-game AI strength.",
                         "Human references and full-information solver are diagnostics only, never pass/fail gates.",
                         "Reported usage covers successful decisions; a partially failed decision may have unreported billed tokens."],
        "cases": {}, "trials": [], "summary": {},
    }

    def save():
        report["summary"] = summarize(report["trials"])
        report["paired_complete_comparison"] = paired_summary(report["trials"], arms)
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix(path.suffix + ".tmp")
            temp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temp.replace(path)

    save()
    for case in cases:
        state = player_state(case.position)
        report["cases"][case.id] = {"visible_state": state, "topic": case.topic,
                                    "reference_preference": case.preferred, "reference_caveat": case.caveat,
                                    "full_information_winning_actions": oracle_actions(case.position)}
    jobs = [(c.id, i, arm) for c in cases for i in range(repeats) for arm in arms]
    random.Random(seed).shuffle(jobs)
    report["planned_decisions"] = len(jobs)
    for case_id, repetition, arm in jobs:
        case = report["cases"][case_id]
        state = case["visible_state"]
        trial = {"case_id": case_id, "repetition": repetition, "arm": arm}
        start = time.perf_counter()
        try:
            if arm == "current_jev":
                decision = decide(state, backend)
            else:
                analysis = score_actions(state)
                decision = choose_simulation(analysis) if arm == "simulation" else choose_hybrid(state, analysis, backend)
                trial["planning_analysis"] = analysis
            trial["decision_seconds"] = time.perf_counter() - start
            legal_ids = {a["id"] for a in state["legal_actions"]}
            if decision["action_id"] not in legal_ids:
                raise ValueError("策略返回非法动作")
            # 评测续局与计划续局分离；相同场景的三组共享随机数与牌分配。
            if "evaluation_analysis" not in case:
                case["evaluation_analysis"] = score_actions(state, policies=EVALUATION_POLICIES,
                                                            seeds=(seed + 10000, seed + 10001))
            evaluated = next(a for a in case["evaluation_analysis"]["actions"] if a["action_id"] == decision["action_id"])
            profiles = evaluated["by_continuation_policy"]
            outcomes = {key: sum(p[key] for p in profiles.values()) / len(profiles)
                        for key in ("team_win_mass", "team_loss_mass", "truncated_mass", "reward_lower_bound", "reward_upper_bound")}
            outcomes["by_policy"] = profiles
            trial.update(decision=decision, outcomes=outcomes, diagnostics={
                "human_reference_agreement": decision["action_id"] in case["reference_preference"],
                "full_information_winning_action": decision["action_id"] in case["full_information_winning_actions"],
            })
        except TypeSafeError as exc:
            trial["execution_error"] = str(exc)
        report["trials"].append(trial)
        save()
        if progress:
            progress(trial, len(report["trials"]), len(jobs))
    report["status"] = "completed_with_execution_errors" if any("execution_error" in t for t in report["trials"]) else "completed"
    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    save()
    return report


def main():
    parser = argparse.ArgumentParser(description="斗地主首步决策：JEV / 模拟 / 模拟加 JEV")
    parser.add_argument("--live", action="store_true", help="调用 API 运行三组；默认仅运行本地模拟")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--model", default="jev-1.13.0")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.repeats <= 0 or Path(args.output).exists():
        parser.error("repeats 必须为正，output 必须是新路径")
    backend = TypeSafeBackend.from_env(args.env_file) if args.live else None
    if backend:
        backend.model = args.model

    def progress(trial, done, total):
        print(json.dumps({"progress": "%d/%d" % (done, total), "case": trial["case_id"],
                          "arm": trial["arm"], "action": trial.get("decision", {}).get("action_id"),
                          "execution_error": trial.get("execution_error")}, ensure_ascii=False), flush=True)

    result = benchmark(backend, args.repeats, args.seed, args.output, progress=progress)
    print(json.dumps(result["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
