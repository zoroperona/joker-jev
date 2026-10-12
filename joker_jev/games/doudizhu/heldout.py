"""预先固定的新快照；不带人工动作标注，不调用求解器筛选。"""

from dataclasses import asdict
import hashlib
import json
import random

from .strategy import DECK, Position, RANKS, ordered
from collections import Counter


def make_cases(seed=20261012, count=2):
    if count <= 0:
        raise ValueError("count 必须为正")
    rng = random.Random(seed)
    cases = []
    for index in range(count):
        pool = [r for r in RANKS for _ in range(1 if r in ("SJ", "BJ") else 2)]
        rng.shuffle(pool)
        pos = Position(tuple(ordered(pool[i * 3:(i + 1) * 3]) for i in range(3)), index % 3)
        pos.validate()
        cases.append({"id": "generated_%03d" % index, "position": pos})
    return cases


SCENARIO_KINDS = ("uneven_lead", "respond_single", "respond_pair", "landlord_one", "landlord_two")


def make_mixed_cases(seed=20261014, count=50):
    """按结构预先分层，绝不按胜负、可赢性或模型选择筛选。"""
    if count <= 0:
        raise ValueError("count 必须为正")
    rng = random.Random(seed)
    cases = []
    for index in range(count):
        scenario = SCENARIO_KINDS[index % len(SCENARIO_KINDS)]
        sizes = [4, 2, 3]
        rng.shuffle(sizes)
        if scenario == "landlord_one":
            sizes = [1, rng.randint(2, 4), rng.randint(2, 4)]
        elif scenario == "landlord_two":
            sizes = [2, rng.randint(3, 4), rng.randint(3, 4)]
        pool = [r for r in RANKS for _ in range(1 if r in ("SJ", "BJ") else 2)]
        rng.shuffle(pool)
        hands, offset = [], 0
        for size in sizes:
            hands.append(ordered(pool[offset:offset + size]))
            offset += size
        actor = (index // len(SCENARIO_KINDS)) % 3
        target, owner, passes = (), None, 0
        responding = scenario in ("respond_single", "respond_pair") or (
            scenario in ("landlord_one", "landlord_two") and (index // len(SCENARIO_KINDS)) % 2 == 0)
        if responding:
            available = DECK - Counter(c for h in hands for c in h)
            width = 2 if scenario == "respond_pair" else 1
            ranks = [r for r in RANKS if available[r] >= width]
            target = (rng.choice(ranks),) * width
            passes = rng.randrange(2)
            owner = (actor - 1 - passes) % 3
        pos = Position(tuple(hands), actor, target, owner, passes)
        pos.validate()
        cases.append({"id": "mixed_%03d" % index, "scenario_kind": scenario, "position": pos})
    return cases


def manifest(cases, seed, generator="doudizhu_snapshot_v1"):
    entries = [{"id": c["id"], "position": asdict(c["position"]),
                **({"scenario_kind": c["scenario_kind"]} if "scenario_kind" in c else {})} for c in cases]
    payload = {"generator": generator, "seed": seed, "cases": entries}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return {**payload, "sha256": digest,
            "scope": "Synthetic unseen snapshots fixed before this run; not histories from full deals. No filtering by solver or JEV. Once examined these become development data, not permanently held-out data."}
