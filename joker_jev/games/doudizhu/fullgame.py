"""固定新快照、轮换三个目标座位，可均衡分配四种风格的完整残局对照。"""

import argparse
import hashlib
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import random

from joker_jev.agents.typesafe import TypeSafeBackend
from .episode import ARMS, run_episode, write_json
from .heldout import make_cases, make_mixed_cases, manifest
from .strategy import SEATS


def metrics(episodes):
    completed = [e for e in episodes if e["status"] == "completed"]
    ledger = [call for e in episodes for call in e["api_ledger"]]
    usage = Counter()
    for call in ledger:
        usage.update({k: v for k, v in call.get("usage", {}).items() if isinstance(v, (int, float))})
    focal = [t for e in episodes for t in e["trace"] if t["player"] == e["focal_seat"]]
    return {
        "attempted": len(episodes), "completed": len(completed),
        "status_counts": dict(Counter(e["status"] for e in episodes)),
        "team_wins": sum(e["team_reward"] == 1 for e in completed),
        "team_losses": sum(e["team_reward"] == -1 for e in completed),
        "mean_completed_team_reward": sum(e["team_reward"] for e in completed) / len(completed) if completed else None,
        "mean_episode_seconds": sum(e["elapsed_seconds"] for e in episodes) / len(episodes) if episodes else None,
        "focal_decisions_attempted": len(focal),
        "focal_nonforced_decisions": sum(not t.get("decision", {}).get("forced", False) for t in focal),
        "api_attempts": len(ledger), "api_errors": sum(c["status"] == "api_error" for c in ledger),
        "known_usage": dict(usage), "usage_unknown_calls": sum(c.get("usage_unknown", False) for c in ledger),
        "model_versions": sorted({c["model"] for c in ledger if c.get("model")}),
    }


def summarize(episodes, arms):
    result = {arm: {"overall": metrics([e for e in episodes if e["arm"] == arm]),
                    "by_seat": {seat: metrics([e for e in episodes if e["arm"] == arm and e["focal_seat"] == seat]) for seat in SEATS},
                    "by_farmer_style": {style: metrics([e for e in episodes if e["arm"] == arm and e["farmer_style"] == style])
                                        for style in sorted({e["farmer_style"] for e in episodes})},
                    "by_profile": {profile: metrics([e for e in episodes if e["arm"] == arm and e.get("profile") == profile])
                                   for profile in sorted({e.get("profile", "legacy") for e in episodes})}}
              for arm in arms}
    groups = {}
    for episode in episodes:
        key = (episode["case_id"], episode["focal_seat"], episode["farmer_style"], episode.get("landlord_style", "pressure"), episode["repetition"])
        if episode["status"] == "completed":
            groups.setdefault(key, {})[episode["arm"]] = episode
    paired = [g for g in groups.values() if set(g) == set(arms)]
    return {"all_attempts": result,
            "paired_complete": {"setting_count": len(paired),
                                "arms": {arm: metrics([g[arm] for g in paired]) for arm in arms}}}


def run_suite(output, backend_factory=None, count=2, repeats=1, seed=20261012, workers=3, progress=None, balanced=False, scenario_set="equal"):
    if scenario_set not in ("equal", "mixed"):
        raise ValueError("未知残局集合")
    if count <= 0 or repeats <= 0 or not 1 <= workers <= 4:
        raise ValueError("count/repeats 必须为正，workers 范围 1 至 4")
    path = Path(output)
    traces = path.parent / (path.stem + "-episodes")
    if path.exists() or traces.exists():
        raise ValueError("报告或逐局目录已存在，请使用新路径")
    cases = (make_mixed_cases if scenario_set == "mixed" else make_cases)(seed, count)
    arms = ARMS if backend_factory else ("simulation",)
    report = {
        "protocol": "doudizhu_full_endgame_v2", "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "running", "manifest": manifest(cases, seed, "doudizhu_mixed_v1" if scenario_set == "mixed" else "doudizhu_snapshot_v1"), "arms": arms,
        "repeats": repeats, "workers": workers, "balanced_profiles": balanced, "scenario_set": scenario_set,
        "scope": ["Each designated strategy acts on every turn of its focal seat, until natural terminal or execution error.",
                  "The same fixed card assignment is used for all arms; the focal strategy occupies each seat in turn.",
                  "Nonfocal seats use the frozen setting profile; legacy mode uses pressure landlord and cooperative/greedy farmers.",
                  "When focal is landlord the style describes both opponents; when focal is farmer it describes the teammate.",
                  "Views carry public history since the snapshot; beliefs update card counts but do not model behavioral evidence from passes.",
                  "No human action labels or omniscient solver are used. API errors and turn caps are not losses.",
                  "Small synthetic endgames, not complete 54-card games or a population-strength estimate."],
        "episodes": [], "summary": summarize([], arms),
    }
    # 在发出任何 API 请求前固定案例及其哈希；全信息 manifest 仅供研究者，不送给 Agent。
    write_json(path, report)
    jobs = []
    profiles = ("random", "pressure", "conservative", "cooperative")
    settings = []
    for index, case in enumerate(cases):
        for seat_index, seat in enumerate(SEATS):
            styles = (profiles[(index * 3 + seat_index) % 4],) if balanced else ("cooperative", "greedy")
            for style in styles:
                landlord_style = style if balanced else "pressure"
                for repetition in range(repeats):
                    identity = [seed, case["id"], seat, style, landlord_style, repetition]
                    setting_seed = int(hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:12], 16)
                    settings.append(dict(case_id=case["id"], focal_seat=seat, farmer_style=style,
                                         landlord_style=landlord_style, repetition=repetition, seed=setting_seed))
                    for arm in arms:
                        jobs.append((case, seat, style, landlord_style, repetition, arm, setting_seed))
    report["settings"] = settings
    random.Random(seed).shuffle(jobs)
    report["planned_episodes"] = len(jobs)
    write_json(path, report)

    def run(job):
        case, seat, style, landlord_style, repetition, arm, setting_seed = job
        job_id = "%s-%s-%s-%d-%s" % (case["id"], seat, style, repetition, arm)
        filename = traces / (job_id + ".json")
        backend = backend_factory() if arm != "simulation" else None
        episode = run_episode(case["position"], arm, seat, style, setting_seed, backend, output=filename, landlord_style=landlord_style)
        episode.update(scenario_kind=case.get("scenario_kind", "equal_three"), profile=style if balanced else "pressure/" + style, case_id=case["id"], repetition=repetition, episode_id=job_id)
        write_json(filename, episode)
        return episode, str(filename.relative_to(path.parent))

    completed = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(run, job) for job in jobs]
        for future in as_completed(futures):
            episode, trace_path = future.result()
            completed.append(episode)
            report["episodes"].append({k: v for k, v in episode.items() if k not in ("trace", "public_history")})
            report["episodes"][-1]["trace_path"] = trace_path
            report["summary"] = summarize(completed, arms)
            write_json(path, report)
            if progress:
                progress(episode, len(completed), len(jobs))
    report["status"] = "completed" if all(e["status"] == "completed" for e in completed) else "completed_with_incomplete_episodes"
    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    write_json(path, report)
    return report


def main():
    parser = argparse.ArgumentParser(description="每步重新决策的完整斗地主小残局")
    parser.add_argument("--scenario-set", choices=("equal", "mixed"), default="equal")
    parser.add_argument("--balanced", action="store_true", help="预先均衡分配四种风格，每副牌每个座位一个风格")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", required=True)
    parser.add_argument("--cases", type=int, default=2)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--seed", type=int, default=20261012)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--model", default="jev-1.13.0")
    parser.add_argument("--env-file", default=".env")
    args = parser.parse_args()
    def backend_factory():
        backend = TypeSafeBackend.from_env(args.env_file)
        backend.model = args.model
        return backend
    def progress(episode, done, total):
        print("%d/%d %s %s reward=%s" % (done, total, episode["episode_id"], episode["status"], episode["team_reward"]), flush=True)
    run_suite(args.output, backend_factory if args.live else None, args.cases, args.repeats,
              args.seed, args.workers, progress, args.balanced, args.scenario_set)


if __name__ == "__main__":
    main()
