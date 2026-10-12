"""从 54 张发牌开始的完整对局，包含叫地主、分层 JEV 选择和逐步日志。"""

import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

from joker_jev.agents.base import Agent
from joker_jev.agents.typesafe import TypeSafeBackend, TypeSafeError
from joker_jev.core.engine import play, TurnLimitError
from joker_jev.games.doudizhu.episode import MeteredBackend, write_json
from .agents import FullSimpleAgent, FullJEVAgent, StrategicJEVAgent, CompactStrategicJEVAgent, visible_payload
from .game import FullDoudizhuGame, PLAYERS


class TracedAgent(Agent):
    def __init__(self, agent, report, save):
        self.agent, self.report, self.save = agent, report, save

    def decide(self, context):
        record = {'player': context.observation.player_id, 'turn': context.observation.turn,
                  'visible_state': visible_payload(context), 'status': 'deciding',
                  'legal_action_ids': [a.id for a in context.observation.legal_actions]}
        self.report['trace'].append(record)
        self.save()
        try:
            decision = self.agent.decide(context)
        finally:
            record['selection'] = getattr(self.agent, 'last_selection', [])
            if getattr(self.agent, 'last_features', None) is not None:
                record['strategy_features'] = self.agent.last_features
            self.save()
        action = next(a for a in context.observation.legal_actions if a.id == decision.action_id)
        record.update(status='selected', decision=asdict(decision), action=asdict(action),
                      selection=getattr(self.agent, 'last_selection', []))
        if getattr(self.agent, 'last_features', None) is not None:
            record['strategy_features'] = self.agent.last_features
        self.save()
        return decision


def run_episode(seed, focal, output, backend=None, max_turns=1000, strategy="v1"):
    if strategy not in ("v1", "v2", "v2_compact"):
        raise ValueError("未知 JEV 策略版本")
    if Path(output).exists():
        raise ValueError('逐局输出路径已存在')
    if focal not in PLAYERS:
        raise ValueError('未知目标座位')
    report = {'seed': seed, 'focal': focal, 'strategy': 'jev' if backend else 'simple_selfplay',
              'strategy_version': strategy if backend else 'full_simple_v1',
              'status': 'running', 'team_reward': None, 'rewards': None, 'trace': [], 'api_ledger': []}
    def save():
        write_json(output, report)
    save()
    metered = MeteredBackend(backend, report['api_ledger'], save) if backend else None
    jev_class = {'v1': FullJEVAgent, 'v2': StrategicJEVAgent, 'v2_compact': CompactStrategicJEVAgent}[strategy]
    agents = {p: TracedAgent(jev_class(metered) if metered and p == focal else FullSimpleAgent(), report, save)
              for p in PLAYERS}
    def step(event):
        row = report['trace'][-1]
        row.update(status='applied', public_events=[asdict(e) for e in event['events']],
                   decision_seconds=event['decision_seconds'], rewards=event['rewards'])
        save()
    started = time.perf_counter()
    try:
        result = play(FullDoudizhuGame(), agents, seed=seed, max_turns=max_turns, on_step=step)
        finish = result.history[-1].data
        report.update(status='completed', turns=result.turns, rewards=result.rewards,
                      team_reward=1 if result.rewards[focal] > 0 else -1,
                      focal_role='landlord' if finish['landlord'] == focal else 'farmer',
                      finish=finish, public_history=[asdict(e) for e in result.history])
    except TypeSafeError as exc:
        report.update(status='api_error', error=str(exc),
                      error_kind='response_validation' if report['api_ledger'] and report['api_ledger'][-1]['status'] == 'completed' else 'request')
    except TurnLimitError as exc:
        report.update(status='turn_limit', error=str(exc))
    except Exception as exc:
        report.update(status='implementation_error', error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        report['elapsed_seconds'] = time.perf_counter() - started
        save()
    return report


def summarize(episodes):
    completed = [e for e in episodes if e['status'] == 'completed']
    ledger = [c for e in episodes for c in e['api_ledger']]
    usage = Counter()
    for call in ledger:
        usage.update({k: v for k, v in call.get('usage', {}).items() if isinstance(v, (int, float))})
    wins = sum(e['team_reward'] == 1 for e in completed)
    return {'attempted': len(episodes), 'completed': len(completed), 'team_wins': wins,
            'team_losses': len(completed) - wins, 'completed_win_rate': wins / len(completed) if completed else None,
            'status_counts': dict(Counter(e['status'] for e in episodes)),
            'mean_completed_score': sum(e['rewards'][e['focal']] for e in completed) / len(completed) if completed else None,
            'api_error_episodes': sum(e['status'] == 'api_error' for e in episodes),
            'response_validation_errors': sum(e['status'] == 'api_error' and bool(e['api_ledger']) and e['api_ledger'][-1]['status'] == 'completed' for e in episodes),
            'api_attempts': len(ledger), 'api_errors': sum(c['status'] == 'api_error' for c in ledger),
            'known_usage': dict(usage), 'unknown_usage_calls': sum(c.get('usage_unknown', False) for c in ledger),
            'model_versions': sorted({c['model'] for c in ledger if c.get('model')}),
            'by_role': {role: {'completed': sum(e['focal_role'] == role for e in completed),
                               'wins': sum(e['focal_role'] == role and e['team_reward'] == 1 for e in completed)}
                        for role in ('landlord', 'farmer')}}


def run_suite(output, count=10, seed=20261016, backend_factory=None, progress=None, strategy="v1"):
    if strategy not in ("v1", "v2", "v2_compact"):
        raise ValueError("未知 JEV 策略版本")
    if count <= 0:
        raise ValueError('count 必须为正')
    path = Path(output)
    traces = path.parent / (path.stem + '-episodes')
    if path.exists() or traces.exists():
        raise ValueError('报告或逐局目录已存在')
    settings = [{'seed': seed + i, 'focal': PLAYERS[i % 3]} for i in range(count)]
    game = FullDoudizhuGame()
    deals = []
    for setting in settings:
        initial = game.initial_state(setting['seed'])
        deals.append({'hands': initial.hands, 'bottom': initial.bottom, 'first_bidder': PLAYERS[initial.actor]})
    manifest = {'rules_version': 'classic_scored_v1', 'settings': settings, 'initial_deals': deals}
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    report = {'protocol': 'full_doudizhu_v1', 'status': 'running', 'manifest': manifest, 'sha256': digest,
              'strategy': 'jev' if backend_factory else 'simple_selfplay', 'strategy_version': strategy,
              'started_at': datetime.now(timezone.utc).isoformat(), 'episodes': []}
    write_json(path, report)  # 所有种子、座位与首轮发牌在请求前冻结；不输送给 Agent。
    episodes = []
    for i, setting in enumerate(settings):
        filename = traces / ('game_%03d.json' % i)
        episode = run_episode(setting['seed'], setting['focal'], filename,
                              backend_factory() if backend_factory else None, strategy=strategy)
        episodes.append(episode)
        entry = {k: v for k, v in episode.items() if k not in ('trace', 'public_history')}
        entry['trace_path'] = str(filename.relative_to(path.parent))
        report['episodes'].append(entry)
        report['summary'] = summarize(episodes)
        write_json(path, report)
        if progress:
            progress(episode, i + 1, count)
    report.update(status='completed' if all(e['status'] == 'completed' for e in episodes) else 'completed_with_incomplete_episodes',
                  completed_at=datetime.now(timezone.utc).isoformat())
    write_json(path, report)
    render(path, report)
    return report


def render(path, report):
    m = report['summary']
    live = report['strategy'] == 'jev'
    label = 'JEV 对简单 AI' if live else '简单 AI 自对弈'
    win_rate = '无已完成局' if m['completed_win_rate'] is None else '%.1f%%' % (100 * m['completed_win_rate'])
    lines = ['# 完整斗地主：' + label, '',
             '每场从 54 张发牌开始，经过叫地主、底牌公开、完整牌型出牌到自然终局。规则为经典叫分制，含炸弹、王炸、春天/反春天积分。', '',
             '目标座位轮换 p0/p1/p2，身份由本局叫分决定；其余两位都是简单 AI，包含目标农民的队友。', '',
             '完成 %d/%d 场；目标团队 %d 胜、%d 负，已完成局胜率 **%s**；目标平均积分 %s。' % (
                 m['completed'], m['attempted'], m['team_wins'], m['team_losses'], win_rate, m['mean_completed_score']),
             '这是 `%s` 的结果；自对弈时目标只是记账座位，不是 JEV。' % report['strategy'], '',
             'API 尝试 %d 次，请求错误 %d 次，已知用量 `%s`，未知用量调用 %d 次，实际模型 `%s`。' % (
                 m['api_attempts'], m['api_errors'], m['known_usage'], m['unknown_usage_calls'], ', '.join(m['model_versions']) or '无 API'), '',
             '冻结设置 SHA-256：`%s`。不因输赢替换种子，不把接口失败或步数上限当输局。' % report['sha256'], '',
             '| 场次 | 种子 | 目标座位 | 最终身份 | 结果 | 积分 | 回合 | 回放 |', '|---|---:|---|---|---|---:|---:|---|']
    for i, e in enumerate(report['episodes'], 1):
        outcome = ('胜' if e['team_reward'] == 1 else '负') if e['status'] == 'completed' else e['status']
        score = e['rewards'][e['focal']] if e['rewards'] else None
        lines.append('| %d | %d | %s | %s | %s | %s | %s | [JSON](%s) |' % (
            i, e['seed'], e['focal'], e.get('focal_role', '未结束'), outcome, score, e.get('turns', '—'), e['trace_path']))
    lines += ['', '小样本和单一启发式对手不代表普遍实力；身份由叫分产生，也不是随机分组的角色对比。策略不要求最优，胜率不是软件通过门槛。', '',
              '[完整规则](../docs/full-doudizhu.md) · [原始数据](%s)' % path.name, '']
    path.with_suffix('.md').write_text('\n'.join(lines), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--strategy', choices=('v1', 'v2', 'v2_compact'), default='v2_compact')
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--episodes', type=int, default=10)
    parser.add_argument('--seed', type=int, default=20261016)
    parser.add_argument('--output', required=True)
    parser.add_argument('--env-file', default='.env')
    parser.add_argument('--model', default='jev-1.13.0')
    args = parser.parse_args()
    def factory():
        backend = TypeSafeBackend.from_env(args.env_file)
        backend.model = args.model
        return backend
    def progress(episode, done, total):
        print('%d/%d seed=%d focal=%s role=%s status=%s team_reward=%s' % (
            done, total, episode['seed'], episode['focal'], episode.get('focal_role'),
            episode['status'], episode['team_reward']), flush=True)
    run_suite(args.output, args.episodes, args.seed, factory if args.live else None, progress, args.strategy)


if __name__ == '__main__':
    main()
