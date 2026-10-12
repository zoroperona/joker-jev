"""固定问题文本，仅比较是否提供显式控制事实；逐次保存结果。"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import random

from joker_jev.agents.typesafe import TypeSafeBackend, TypeSafeError
from .scenarios import COOPERATION_SCENARIOS
from .strategy import oracle_actions, player_state
from .tactics import ACTION_INSTRUCTIONS, QUESTIONS, decide


def summary(trials):
    result = {}
    for arm in ("baseline", "control_facts"):
        attempted = [t for t in trials if t["arm"] == arm]
        completed = [t for t in attempted if "decision" in t]
        result[arm] = {
            "attempted": len(attempted), "completed": len(completed),
            "errors": len(attempted) - len(completed),
            "human_reference_agreements": sum(t["human_reference_agreement"] for t in completed),
            "full_information_winning_choices": sum(t["full_information_winning"] for t in completed),
            "forced_decisions": sum(t["decision"]["forced"] for t in completed),
        }
    return result


def compare(backend, repeats=3, seed=2026, output=None, progress=None):
    if repeats <= 0:
        raise ValueError("repeats 必须大于 0")
    path = Path(output) if output else None
    if path and path.exists():
        raise ValueError("报告已存在，请使用新路径以保留原始结果")
    cases = {}
    for case in COOPERATION_SCENARIOS:
        baseline = player_state(case.position)
        enhanced = player_state(case.position, include_control_facts=True)
        winners = oracle_actions(case.position)
        if not set(case.preferred) <= {a["id"] for a in baseline["legal_actions"]}:
            raise ValueError("参考建议包含非法动作: " + case.id)
        cases[case.id] = {
            "topic": case.topic, "preferred": case.preferred, "rationale": case.rationale,
            "caveat": case.caveat, "full_information_winning_actions": winners,
               "reference_subset_of_full_information_wins": set(case.preferred) <= set(winners),
            "states": {"baseline": baseline, "control_facts": enhanced},
        }
    pairs = [(case_id, repetition) for case_id in cases for repetition in range(repeats)]
    rng = random.Random(seed)
    rng.shuffle(pairs)
    jobs = []
    for case_id, repetition in pairs:
        arms = ["baseline", "control_facts"]
        rng.shuffle(arms)
        jobs.extend((case_id, repetition, arm) for arm in arms)
    report = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "suite_version": "doudizhu_cooperation_v1", "status": "running",
        "report_schema_version": 2,
        "requested_model": backend.model, "repeats": repeats, "schedule_seed": seed,
        "planned_trials": len(jobs), "questions": QUESTIONS, "action_instructions": ACTION_INSTRUCTIONS,
        "intervention": "Only add belief.facts.control; no question changes, forced tactical rules or hidden information.",
        "limitations": ["八个人工回归场景，含点数变体，不是独立泛化测试。",
                         "同场景重复调用相关；匹配率不是胜率，不能据此判断统计显著性。",
                         "preferred 是带假设的战术偏好；全知穷举仅作参考底牌诊断。"],
        "cases": cases, "trials": [], "summary": summary([]),
    }

    def save():
        report["summary"] = summary(report["trials"])
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temporary.replace(path)

    save()
    for case_id, repetition, arm in jobs:
        case = cases[case_id]
        trial = {"case_id": case_id, "repetition": repetition, "arm": arm}
        try:
            decision = decide(case["states"][arm], backend)
            trial.update(decision=decision, human_reference_agreement=decision["action_id"] in case["preferred"],
                         full_information_winning=decision["action_id"] in case["full_information_winning_actions"])
        except TypeSafeError as exc:
            trial["error"] = str(exc)
        report["trials"].append(trial)
        save()
        if progress:
            progress(trial, len(report["trials"]), len(jobs))
    report["status"] = "completed_with_errors" if any("error" in t for t in report["trials"]) else "completed"
    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    save()
    return report


def main():
    parser = argparse.ArgumentParser(description="斗地主协作场景：公开控制事实 A/B 对照")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--model", default="jev-1.13.0", help="固定版本以避免 alias 漂移")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.repeats <= 0 or Path(args.output).exists():
        parser.error("repeats 必须为正，output 必须为尚不存在的新报告路径")
    backend = TypeSafeBackend.from_env(args.env_file)
    backend.model = args.model

    def progress(trial, done, total):
        print(json.dumps({"progress": "%d/%d" % (done, total), "case": trial["case_id"],
                          "arm": trial["arm"], "match": trial.get("human_reference_agreement"),
                          "error": trial.get("error")}, ensure_ascii=False), flush=True)

    report = compare(backend, args.repeats, args.seed, args.output, progress)
    print(json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
