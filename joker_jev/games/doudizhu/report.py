"""从已保存的完整残局记录生成描述性报告，不调用模型或修改实验结果。"""

import argparse
from collections import Counter
import json
from pathlib import Path


def behavior_counts(episodes):
    counts = Counter()
    for episode in episodes:
        for row in episode['trace']:
            if row['player'] != episode['focal_seat'] or row['status'] != 'applied':
                continue
            view = row['visible_state']
            action = next(a for a in view['legal_actions'] if a['id'] == row['decision']['action_id'])
            active = view['public']['active_play']
            payload = action['payload']
            counts['applied_decisions'] += 1
            if row['decision'].get('forced'):
                counts['forced'] += 1
                continue
            counts['nonforced'] += 1
            counts['break_pair'] += bool(payload['breaks_pair'])
            counts['play_pair'] += payload['kind'] == 'pair'
            if active['cards']:
                teammate_owns = active['owner'] == view['self']['teammate']
                prefix = 'teammate' if teammate_owns else 'opponent'
                counts[prefix + '_owns'] += 1
                counts[prefix + ('_passed' if not payload['cards'] else '_overtaken')] += 1
            else:
                counts['free_lead'] += 1
    return dict(counts)


def setting_key(e):
    return (e['case_id'], e['focal_seat'], e['farmer_style'], e['landlord_style'], e['repetition'])


def render(path, local_path=None):
    path = Path(path)
    report = json.loads(path.read_text())
    if report['status'] == 'running':
        raise ValueError('实验未结束，不能生成最终报告')
    episodes = [json.loads((path.parent / e['trace_path']).read_text()) for e in report['episodes']]
    baseline_note = ''
    if local_path:
        local = json.loads(Path(local_path).read_text())
        if local['manifest'] != report['manifest'] or local['settings'] != report['settings']:
            raise ValueError('本地和线上实验设置不一致')
        expected = {setting_key(e): (e['status'], e['team_reward']) for e in local['episodes']}
        observed = {setting_key(e): (e['status'], e['team_reward']) for e in episodes if e['arm'] == 'simulation'}
        if expected != observed:
            raise ValueError('本地和线上纯模拟结果不一致')
        baseline_note = '\n本地与线上 manifest、全部设置以及逐设置纯模拟终局收益完全一致。\n'
    arms = report['arms']
    summary = report['summary']
    lines = [f"# {len(report['manifest']['cases'])} 副固定残局：逐步决策对照", '',
             f"实验状态：`{report['status']}`；案例数 {len(report['manifest']['cases'])}，设置数 {len(report['settings'])}，对局数 {len(episodes)}。",
             f"\n案例 SHA-256：`{report['manifest']['sha256']}`。", baseline_note,
             '## 全部尝试', '',
             '| 策略 | 完成/尝试 | 胜/负 | 平均团队收益 | API 错误 | API 次数 | 已知输入/输出 token | 平均每局秒 |',
             '|---|---:|---:|---:|---:|---:|---:|---:|']
    for arm in arms:
        m = summary['all_attempts'][arm]['overall']
        usage = m['known_usage']
        reward = m['mean_completed_team_reward']
        lines.append(f"| {arm} | {m['completed']}/{m['attempted']} | {m['team_wins']}/{m['team_losses']} | {reward if reward is None else round(reward, 4)} | {m['api_errors']} | {m['api_attempts']} | {usage.get('input_tokens', 0)}/{usage.get('output_tokens', 0)} | {m['mean_episode_seconds']:.3f} |")
    lines += ['', '收益为团队赢 +1、输 -1；API 错误和步数上限不计输局。耗时含本地计算、网络等待和并发影响；token 是接口返回的已知用量，不代表已核对账单。', '',
              f"三种策略都完成的匹配设置：{summary['paired_complete']['setting_count']}。", '',
              '| 策略 | 匹配设置胜/负 | 匹配平均收益 | 未知用量调用 | 实际模型 |',
              '|---|---:|---:|---:|---|']
    for arm in arms:
        m = summary['paired_complete']['arms'][arm]
        all_m = summary['all_attempts'][arm]['overall']
        reward = m['mean_completed_team_reward']
        lines.append(f"| {arm} | {m['team_wins']}/{m['team_losses']} | {reward if reward is None else round(reward, 4)} | {all_m['usage_unknown_calls']} | {', '.join(all_m['model_versions']) or '无 API'} |")
    for dimension, title in [('by_seat', '按目标座位'), ('by_profile', '按预先分配风格')]:
        lines += ['', '## ' + title, '', '| 分组 | 策略 | 完成/尝试 | 胜/负 | 平均收益 |', '|---|---|---:|---:|---:|']
        for group in summary['all_attempts'][arms[0]][dimension]:
            for arm in arms:
                m = summary['all_attempts'][arm][dimension][group]
                reward = m['mean_completed_team_reward']
                lines.append(f"| {group} | {arm} | {m['completed']}/{m['attempted']} | {m['team_wins']}/{m['team_losses']} | {reward if reward is None else round(reward, 4)} |")
    lines += ['', '## 已访问局面的行为描述', '',
              '下表只统计目标座位已执行的非强制动作；分母是该策略实际访问的局面数量，不是同一批决策机会。因此只能描述行为，不能据此判定哪种策略更正确。', '',
              '| 策略 | 非强制动作 | 队友掌权时让牌/机会 | 队友掌权时接管/机会 | 对手掌权时接管/机会 | 拆对子 | 出对子 |',
              '|---|---:|---:|---:|---:|---:|---:|']
    for arm in arms:
        c = Counter(behavior_counts([e for e in episodes if e['arm'] == arm]))
        lines.append(f"| {arm} | {c['nonforced']} | {c['teammate_passed']}/{c['teammate_owns']} | {c['teammate_overtaken']}/{c['teammate_owns']} | {c['opponent_overtaken']}/{c['opponent_owns']} | {c['break_pair']} | {c['play_pair']} |")
    groups = {}
    for e in episodes:
        if e['status'] == 'completed':
            groups.setdefault(setting_key(e), {})[e['arm']] = e
    if 'simulation' in arms:
        lines += ['', '## 与纯模拟逐设置对照', '',
                  '| 策略 | 同赢 | 同输 | 策略赢/模拟输 | 策略输/模拟赢 |',
                  '|---|---:|---:|---:|---:|']
        for arm in arms:
            if arm == 'simulation':
                continue
            outcomes = Counter((g[arm]['team_reward'], g['simulation']['team_reward'])
                               for g in groups.values() if set(g) == set(arms))
            lines.append(f"| {arm} | {outcomes[(1, 1)]} | {outcomes[(-1, -1)]} | {outcomes[(1, -1)]} | {outcomes[(-1, 1)]} |")
        lines += ['', '终局收益相同不表示出牌路径相同；纯模拟也可能在某些设置输给当前 JEV。所有统计均为本批固定局面的观察，不是最优性证明。']
    disagreements = [g for g in groups.values() if set(g) == set(arms) and len({e['team_reward'] for e in g.values()}) > 1]
    lines += ['', f'完整匹配设置中，有 {len(disagreements)} 个设置出现不同终局收益。以下按案例编号列出前 10 个，供复盘，不作为人工正确答案。', '',
              '| 案例/座位/风格 | ' + ' | '.join(arms) + ' |', '|---|' + '---:|' * len(arms)]
    by_id = {e['episode_id']: e for e in report['episodes']}
    for group in sorted(disagreements, key=lambda g: setting_key(g[arms[0]]))[:10]:
        first = group[arms[0]]
        cells = []
        for arm in arms:
            e = group[arm]
            cells.append(f"[{e['team_reward']}]({by_id[e['episode_id']]['trace_path']})")
        lines.append('| ' + '/'.join([first['case_id'], first['focal_seat'], first['profile']]) + ' | ' + ' | '.join(cells) + ' |')
    lines += ['', '## 适用范围', '',
              '每人三张的合成残局，仅有单牌、对子和王炸，不含完整发牌、叫地主、顺子或倍数规则。三个座位来自同一副牌；均衡模式的风格分配并非全交叉。不能把全部对局视作独立样本，也不能从分组胜率推断风格的因果效果。', '',
              '结果不要求 JEV 最优，不使用人工动作标签或全知解筛选案例。错误、策略收益、调用用量分别记录。查看结果后，这批案例成为开发数据；后续改动应另取新样本验证。', '',
              f'原始记录：[{path.name}]({path.name})；[协议](../docs/full-endgame-evaluation.md)。', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report')
    parser.add_argument('--local')
    args = parser.parse_args()
    Path(args.report).with_suffix('.md').write_text(render(args.report, args.local), encoding='utf-8')


if __name__ == '__main__':
    main()
