"""python3 -m joker_jev.games.doudizhu.evaluate [--agent jev]。"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from joker_jev.agents.typesafe import TypeSafeBackend
from .scenarios import SCENARIOS
from .strategy import oracle_actions, player_state
from .tactics import decide


def evaluate(backend=None, include_control_facts=False):
    rows = []
    for case in SCENARIOS:
        state = player_state(case.position, include_control_facts)
        legal = {a["id"] for a in state["legal_actions"]}
        winners = oracle_actions(case.position)
        if not set(case.preferred) <= legal:
            raise ValueError("参考建议包含非法动作: " + case.id)
        row = {"id": case.id, "topic": case.topic, "preferred": case.preferred,
               "rationale": case.rationale, "caveat": case.caveat,
               "full_information_winning_actions": winners,
               "reference_subset_of_full_information_wins": set(case.preferred) <= set(winners), "visible_state": state}
        if backend is not None:
            decision = decide(state, backend)
            row.update(decision=decision, human_reference_agreement=decision["action_id"] in case.preferred,
                       full_information_winning=decision["action_id"] in winners)
        rows.append(row)
    scored = [r for r in rows if "decision" in r]
    model_rows = [r for r in scored if not r["decision"]["forced"]]
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "suite_version": "doudizhu_endgame_v1",
        "report_schema_version": 2,
        "mode": "jev" if backend is not None else "offline_validation",
        "include_control_facts": include_control_facts,
        "limitations": ["人工构造的策略回归集，不是独立测试集或完整对局胜率。",
                         "preferred 是带假设的战术标注，不能保证所有隐藏牌分配下最优。",
                         "全知穷举知道双方底牌，仅供离线诊断；不代表隐藏信息下的最优策略。",
                         "只覆盖每人最多四张、剩余普通点数不超过两张的小残局。"],
        "summary": {"scenarios": len(rows), "evaluated": len(scored),
                    "model_decisions": len(model_rows), "forced_decisions": len(scored) - len(model_rows),
                    "model_human_reference_agreements": sum(r["human_reference_agreement"] for r in model_rows),
                    "human_reference_agreements": sum(r["human_reference_agreement"] for r in scored),
                    "full_information_winning_choices": sum(r["full_information_winning"] for r in scored)},
        "scenarios": rows,
    }


def main():
    parser = argparse.ArgumentParser(description="斗地主策略残局验证与 JEV 战术评测")
    parser.add_argument("--agent", choices=("offline", "jev"), default="offline")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--control-facts", action="store_true", help="加入公开信息可确定的牌权威胁事实")
    parser.add_argument("--output", help="保存详细 JSON 报告，包含可见状态、标注、判断与用量")
    args = parser.parse_args()
    backend = TypeSafeBackend.from_env(args.env_file) if args.agent == "jev" else None
    report = evaluate(backend, args.control_facts)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"mode": report["mode"], **report["summary"]}, ensure_ascii=False))
    for row in report["scenarios"]:
        if "decision" in row:
            print(json.dumps({"id": row["id"], "action": row["decision"]["action_id"],
                              "human_reference_agreement": row["human_reference_agreement"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
