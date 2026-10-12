"""预先固定开发回归和新牌局，配对比较原版与动作后果增强版 JEV。"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random

from joker_jev.agents.typesafe import TypeSafeBackend
from joker_jev.games.doudizhu.episode import write_json
from .game import FullDoudizhuGame, PLAYERS
from .match import run_episode, summarize
from .diagnose import diagnose


def make_settings(count, fresh_seed=20261201, balanced_fresh=True):
    game = FullDoudizhuGame()
    settings = []
    for split, start in (('development', 20261016), ('fresh', fresh_seed)):
        for i in range(count):
            seed = start + i
            state = game.initial_state(seed)
            settings.append({'split': split, 'seed': seed, 'focal': PLAYERS[(i + (i // 3 if split == 'fresh' and balanced_fresh else 0)) % 3],
                             'initial_hands': state.hands, 'bottom': state.bottom, 'first_bidder': PLAYERS[state.actor]})
    return settings


def run_comparison(output, factory, count=10, workers=3, candidate="v2", fresh_seed=20261101, balanced_fresh=False):
    if candidate not in ("v2", "v2_compact"):
        raise ValueError("未知候选版本")
    if count <= 0 or not 1 <= workers <= 4:
        raise ValueError('count/workers 无效')
    path = Path(output)
    traces = path.parent / (path.stem + '-episodes')
    if path.exists() or traces.exists():
        raise ValueError('报告或对局目录已存在')
    settings = make_settings(count, fresh_seed, balanced_fresh)
    report = {'protocol': 'paired_strategy_v1_v2', 'status': 'running', 'settings': settings,
              'sha256': hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest(),
              'versions': {'v1': 'Original FullJEVAgent, unchanged prompts and choices.',
                           candidate: 'Visible hand partitions (4000 node budget), control and pass consequences, conditional planning instructions. All legal actions retained. JEV still chooses.'},
              'candidate': candidate, 'balanced_fresh': balanced_fresh,
              'candidate_config': {'hand_plan_nodes': 4000, 'final_choice_limit': 24 if candidate == 'v2_compact' else 255,
                                   'repeated_partition_lists_omitted': candidate == 'v2_compact'},
              'started_at': datetime.now(timezone.utc).isoformat(), 'episodes': [],
              'scope': 'Both versions run now with the same model, initial seed and focal seat. Bidding may change roles/deals. No outcome filtering, no hidden hands in agents, no automatic retry. Fresh settings not used to tune v2.'}
    write_json(path, report)
    jobs = [(s, v) for s in settings for v in ('v1', candidate)]
    random.Random(417).shuffle(jobs)
    def run(job):
        setting, version = job
        filename = traces / ('%s-%d-%s.json' % (setting['split'], setting['seed'], version))
        result = run_episode(setting['seed'], setting['focal'], filename, factory(), strategy=version)
        result.update(split=setting['split'], trace_path=str(filename.relative_to(path.parent)))
        write_json(filename, result)
        return result
    done = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for future in as_completed([pool.submit(run, job) for job in jobs]):
            episode = future.result()
            done.append(episode)
            report['episodes'].append({k: v for k, v in episode.items() if k not in ('trace', 'public_history')})
            report['summary'] = summary(done, candidate)
            write_json(path, report)
            print('%d/%d %s %d %s %s reward=%s' % (len(done), len(jobs), episode['split'], episode['seed'],
                                                 episode['strategy_version'], episode['status'], episode['team_reward']), flush=True)
    report.update(status='completed' if all(e['status'] == 'completed' for e in done) else 'completed_with_incomplete_episodes',
                  completed_at=datetime.now(timezone.utc).isoformat())
    write_json(path, report)
    render(path, report)
    return report


def summary(episodes, candidate="v2"):
    out = {}
    for split in ('development', 'fresh'):
        selected = [e for e in episodes if e['split'] == split]
        groups = {}
        for e in selected:
            if e['status'] == 'completed':
                groups.setdefault((e['seed'], e['focal']), {})[e['strategy_version']] = e
        paired = [g for g in groups.values() if set(g) == {'v1', candidate}]
        out[split] = {'all_attempts': {v: summarize([e for e in selected if e['strategy_version'] == v]) for v in ('v1', candidate)},
                      'paired_settings': len(paired),
                      'paired_complete': {v: summarize([g[v] for g in paired]) for v in ('v1', candidate)},
                      'v2_win_v1_loss': sum(g[candidate]['team_reward'] == 1 and g['v1']['team_reward'] == -1 for g in paired),
                      'v1_win_v2_loss': sum(g['v1']['team_reward'] == 1 and g[candidate]['team_reward'] == -1 for g in paired)}
    return out


def render(path, report):
    versions = tuple(report['versions'])
    candidate = report.get('candidate', 'v2')
    lines = ['# 完整斗地主策略调整：配对对照', '',
             'v1 为原始 JEV；候选版本 `%s` 增加玩家可见的拆牌方案、动作后果和有条件的牌权规划提示，最终动作仍由 JEV 选择。未修改简单 AI 对手。' % candidate, '',
             '开发回归集用于复盘；新牌局在评测前冻结且不用于本轮调参。两版本均重新调用同一固定模型，相同初始种子和目标座位；叫分不同可改变最终身份。', '',
             '冻结 SHA-256：`%s`。' % report['sha256'], '',
             '| 数据集 | 版本 | 完成/尝试 | 胜/负 | 胜率 | 平均积分 | API 次数 | 已知输入/输出 token |',
             '|---|---|---:|---:|---:|---:|---:|---:|']
    notes = []
    for split, data in report['summary'].items():
        for v, m in data['all_attempts'].items():
            usage = m['known_usage']; rate = m['completed_win_rate']
            lines.append('| %s | %s | %d/%d | %d/%d | %s | %s | %d | %d/%d |' % (
                split, v, m['completed'], m['attempted'], m['team_wins'], m['team_losses'],
                '—' if rate is None else '%.1f%%' % (100 * rate), m['mean_completed_score'], m['api_attempts'],
                usage.get('input_tokens', 0), usage.get('output_tokens', 0)))
        notes += ['', '%s：两版均完成的配对 %d 个，v2 赢/v1 输 %d 个，v1 赢/v2 输 %d 个。' % (
            split, data['paired_settings'], data['v2_win_v1_loss'], data['v1_win_v2_loss']), '']
    errors = [(e['split'], e['seed'], e['strategy_version'], e.get('error', e['status']))
              for e in report['episodes'] if e['status'] != 'completed']
    if errors:
        notes += ['未完成对局（保留，不计输局）：', '']
        notes += ['- %s / %s / %s：%s' % item for item in errors]
        notes += ['']
    lines += notes
    lines += ['## 逐局结果', '', '| 数据集 | 种子 | v1 结果/身份 | %s 结果/身份 |' % candidate, '|---|---:|---|---|']
    groups = {}
    for e in report['episodes']:
        groups.setdefault((e['split'], e['seed']), {})[e['strategy_version']] = e
    for (split, seed), group in sorted(groups.items()):
        cells = []
        for version in versions:
            e = group[version]
            result = ('胜' if e['team_reward'] == 1 else '负') if e['status'] == 'completed' else e['status']
            cells.append('[%s/%s](%s)' % (result, e.get('focal_role', '未完成'), e['trace_path']))
        lines.append('| %s | %d | %s | %s |' % (split, seed, *cells))
    lines += ['', '接口错误和上限不算输局；配对统计只含双方均完成设置。样本很小、对手单一、叫分影响身份，不能据此证明普遍优势或最优性。完整指标和调用记录见 [JSON](%s)。' % path.name, '']
    path.with_suffix('.md').write_text('\n'.join(lines), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', choices=('v2', 'v2_compact'), default='v2_compact')
    parser.add_argument('--fresh-seed', type=int, default=20261201)
    parser.add_argument('--output', required=True)
    parser.add_argument('--cases-per-split', type=int, default=10)
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--model', default='jev-1.13.0')
    parser.add_argument('--env-file', default='.env')
    args = parser.parse_args()
    def factory():
        backend = TypeSafeBackend.from_env(args.env_file); backend.model = args.model
        return backend
    run_comparison(args.output, factory, args.cases_per_split, args.workers, args.candidate, args.fresh_seed, True)


if __name__ == '__main__':
    main()
