"""固定 10 场 JEV 对简单 AI 的受限残局；未完成局单列，不重抽或算输。"""

import argparse
from datetime import datetime, timezone
from pathlib import Path

from joker_jev.agents.typesafe import TypeSafeBackend
from .episode import run_episode, write_json
from .fullgame import metrics
from .heldout import make_mixed_cases, manifest
from .strategy import SEATS


def run_match(output, backend_factory=None, seed=20261015, focal_policy='current_jev'):
    if focal_policy not in ('current_jev', 'simple'):
        raise ValueError('仅支持 current_jev 或 simple')
    if focal_policy == 'current_jev' and backend_factory is None:
        raise ValueError('JEV 对局需要后端')
    path = Path(output)
    traces = path.parent / (path.stem + '-episodes')
    if path.exists() or traces.exists():
        raise ValueError('报告或逐局目录已存在')
    cases = make_mixed_cases(seed, 10)
    settings = [{'case_id': c['id'], 'focal_seat': SEATS[i % 3],
                 'scenario_kind': c['scenario_kind'], 'seed': seed + i,
                 'focal_policy': focal_policy, 'other_seats_policy': 'simple_doudizhu_v1'}
                for i, c in enumerate(cases)]
    report = {'protocol': 'jev_vs_simple_endgame_v1', 'status': 'running',
              'started_at': datetime.now(timezone.utc).isoformat(),
              'manifest': manifest(cases, seed, 'doudizhu_mixed_v1'),
              'settings': settings, 'episodes': [],
              'scope': 'Exactly 10 synthetic restricted endgames. Focal seat rotates 4 landlord / 3 farmer_after / 3 farmer_before. Both other seats use simple AI, including focal farmer teammate. Team win rate, not full-deal strength. No outcome filtering or automatic retries.'}
    write_json(path, report)  # 在首次 API 调用前固定全部设置。
    episodes = []
    for case, setting in zip(cases, settings):
        filename = traces / (case['id'] + '.json')
        episode = run_episode(case['position'], focal_policy, setting['focal_seat'],
                              farmer_style='simple', landlord_style='simple', seed=setting['seed'],
                              backend=backend_factory() if focal_policy == 'current_jev' else None,
                              output=filename)
        episode.update(case_id=case['id'], scenario_kind=case['scenario_kind'])
        write_json(filename, episode)
        episodes.append(episode)
        compact = {k: v for k, v in episode.items() if k not in ('trace', 'public_history')}
        compact['trace_path'] = str(filename.relative_to(path.parent))
        report['episodes'].append(compact)
        report['metrics'] = metrics(episodes)
        report['metrics']['completed_team_win_rate'] = (report['metrics']['team_wins'] / report['metrics']['completed']
                                                       if report['metrics']['completed'] else None)
        report['by_seat'] = {seat: metrics([e for e in episodes if e['focal_seat'] == seat]) for seat in SEATS}
        write_json(path, report)
        print('%d/10 %s %s %s reward=%s' % (len(episodes), case['id'], setting['focal_seat'],
                                            episode['status'], episode['team_reward']), flush=True)
    report['status'] = 'completed' if all(e['status'] == 'completed' for e in episodes) else 'completed_with_incomplete_episodes'
    report['completed_at'] = datetime.now(timezone.utc).isoformat()
    write_json(path, report)
    write_markdown(path, report)
    return report


def write_markdown(path, report):
    m = report['metrics']
    win_rate = m['completed_team_win_rate']
    rate_text = '无完整对局' if win_rate is None else '%.1f%%' % (100 * win_rate)
    is_jev = report['settings'][0]['focal_policy'] == 'current_jev'
    title = 'JEV 对简单斗地主 AI' if is_jev else '简单斗地主 AI 自对弈（无 JEV）'
    lines = ['# 10 场：' + title, '',
             '当前支持受限残局，不是完整 54 张斗地主。目标策略轮换座位，另外两个座位使用原创 `simple_doudizhu_v1`；当目标是农民时，队友也是简单 AI。', '',
             '本次目标策略：`%s`。' % report['settings'][0]['focal_policy'], '',
             '完成 %d/%d 场，目标团队 %d 胜、%d 负，已完成局胜率 **%s**。' % (m['completed'], m['attempted'], m['team_wins'], m['team_losses'], rate_text), '',
             'API 调用 %d 次，接口错误 %d 次，已知用量 `%s`，未知用量调用 %d 次，实际模型 `%s`。' % (
                 m['api_attempts'], m['api_errors'], m['known_usage'], m['usage_unknown_calls'], ', '.join(m['model_versions']) or '无 API'), '',
             '## 固定协议', '',
             '- 种子 `%s`；10 副牌在调用前固定，SHA-256 `%s`。' % (report['manifest']['seed'], report['manifest']['sha256']),
             '- 五个结构层各 2 副：手牌不均、跟单牌、跟对子、地主一张、地主两张。',
             '- 地主 4 场，地主下家 3 场，地主上家 3 场；不按胜负或动作筛选。',
             '- 接口错误和步数上限保留为未完成，不算输局，不自动重试。',
             '- AI 只看自己的手牌及公开信息；没有实际对手底牌、全知求解或 JEV 调用。', '',
             '| 场次 | 情况 | 目标身份 | 结果 | 回放 |', '|---|---|---|---|---|']
    for i, e in enumerate(report['episodes'], 1):
        outcome = ('胜' if e['team_reward'] == 1 else '负') if e['status'] == 'completed' else e['status']
        lines.append('| %d | %s | %s | %s | [JSON](%s) |' % (i, e['scenario_kind'], e['focal_seat'], outcome, e['trace_path']))
    lines += ['', '只有 10 场，且身份和局面难度不相同；这是可复现的协议与对局演示，不是稳定实力估计。远程模型输出可能随时间变化。胜率不能用于判定软件测试是否通过。', '',
              '[原始数据](%s) · [AI 设计](../docs/simple-doudizhu-ai.md)' % path.name, '']
    path.with_suffix('.md').write_text('\n'.join(lines), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--seed', type=int, default=20261015)
    parser.add_argument('--model', default='jev-1.13.0')
    parser.add_argument('--env-file', default='.env')
    parser.add_argument('--local', action='store_true', help='简单 AI 自对弈，无 API；不代表 JEV 胜率')
    args = parser.parse_args()
    def factory():
        backend = TypeSafeBackend.from_env(args.env_file)
        backend.model = args.model
        return backend
    run_match(args.output, None if args.local else factory, args.seed, 'simple' if args.local else 'current_jev')


if __name__ == '__main__':
    main()
