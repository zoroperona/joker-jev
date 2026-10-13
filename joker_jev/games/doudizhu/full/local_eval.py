"""离线配对评测（无 API）：同一发牌与目标座位上，比较目标座位使用不同代码策略时的团队结果。"""

import argparse
from concurrent.futures import ProcessPoolExecutor
import json

from joker_jev.core.engine import play
from .agents import FullSimpleAgent, RolloutAgent
from .game import FullDoudizhuGame, PLAYERS


def make_agent(name, rollouts):
    if name == 'simple':
        return FullSimpleAgent()
    if name == 'rollout':
        return RolloutAgent(rollouts=rollouts)
    if name == 'rollout_play':  # 仅出牌使用模拟，叫分沿用简单 AI，用于分离叫分与出牌贡献。
        agent = RolloutAgent(rollouts=rollouts)
        simple = FullSimpleAgent()
        class PlayOnly(RolloutAgent):
            def decide(inner, context):
                if context.observation.public['phase'] == 'bidding':
                    return simple.decide(context)
                return agent.decide(context)
        return PlayOnly()
    raise ValueError('未知策略')


def run_one(job):
    seed, focal, name, rollouts = job
    agents = {p: make_agent(name, rollouts) if p == focal else FullSimpleAgent() for p in PLAYERS}
    result = play(FullDoudizhuGame(), agents, seed=seed)
    landlord = [e for e in result.history if e.kind == 'landlord_selected'][-1].data['landlord']
    score = result.rewards[focal]
    return {'seed': seed, 'focal': focal, 'strategy': name, 'score': score, 'win': score > 0,
            'role': 'landlord' if landlord == focal else 'farmer'}


def summarize(rows):
    out = {}
    for name in sorted({r['strategy'] for r in rows}):
        mine = [r for r in rows if r['strategy'] == name]
        out[name] = {'games': len(mine), 'win_rate': round(sum(r['win'] for r in mine) / len(mine), 3),
                     'mean_score': round(sum(r['score'] for r in mine) / len(mine), 3),
                     'by_role': {role: {'games': sum(r['role'] == role for r in mine),
                                        'wins': sum(r['role'] == role and r['win'] for r in mine)}
                                 for role in ('landlord', 'farmer')}}
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--games', type=int, default=120)
    parser.add_argument('--seed', type=int, default=30000000)
    parser.add_argument('--strategies', default='simple,rollout')
    parser.add_argument('--rollouts', type=int, default=600)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--output')
    args = parser.parse_args()
    jobs = [(args.seed + i, PLAYERS[i % 3], name, args.rollouts)
            for i in range(args.games) for name in args.strategies.split(',')]
    with ProcessPoolExecutor(args.workers) as pool:
        rows = list(pool.map(run_one, jobs, chunksize=1))
    summary = summarize(rows)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if args.output:
        with open(args.output, 'x', encoding='utf-8') as f:
            json.dump({'config': vars(args), 'summary': summary, 'games': rows}, f, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
