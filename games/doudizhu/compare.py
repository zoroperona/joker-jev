"""Paired JEV input comparison against frozen pretrained DouZero (no training)."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1]))
from joker_jev.agents.typesafe import TypeSafeBackend
from joker_jev.games.doudizhu.full.douzero import DouZeroAgent
from joker_jev.games.doudizhu.full.input_modes import MODES
from joker_jev.games.doudizhu.full.match import run_episode, summarize
from joker_jev.games.doudizhu.episode import write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-mode', choices=(*MODES, 'both'), default='both')
    parser.add_argument('--episodes', type=int, default=3, help='每种模式的局数，同种子与座位配对')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--env-file', default=str(ROOT.parents[1] / '.env'))
    parser.add_argument('--model', default='jev-1.13.0')
    parser.add_argument('--models', type=Path, default=ROOT / 'models')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.episodes < 1:
        parser.error('--episodes 必须为正')
    modes = MODES if args.input_mode == 'both' else (args.input_mode,)
    traces = args.output.parent / (args.output.stem + '-episodes')
    if args.output.exists() or traces.exists():
        parser.error('报告路径已存在，请使用新路径')
    backend = TypeSafeBackend.from_env(args.env_file)
    backend.model = args.model
    opponent = DouZeroAgent(args.models)
    settings = [{'seed': args.seed + i, 'focal': 'p%d' % (i % 3)} for i in range(args.episodes)]
    fingerprints = {p.stem: hashlib.sha256(p.read_bytes()).hexdigest() for p in args.models.glob('*.ckpt')}
    report = {'protocol': 'matched_jev_inputs_vs_frozen_douzero_v1', 'status': 'running',
              'settings': settings, 'modes': modes, 'requested_model': args.model,
              'opponent_weight_sha256': fingerprints, 'bidding_policy': 'full_simple_v1 for DouZero seats',
              'started_at': datetime.now(timezone.utc).isoformat(), 'episodes': [], 'summary': {}}
    write_json(args.output, report)
    episodes = {mode: [] for mode in modes}
    for i, setting in enumerate(settings):
        # Alternate mode order, keeping the initial deal and target seat paired.
        for mode in modes if i % 2 == 0 else tuple(reversed(modes)):
            path = traces / ('%03d-%s.json' % (i, mode))
            result = run_episode(**setting, output=path, backend=backend,
                                 opponent_agent=opponent, input_mode=mode)
            episodes[mode].append(result)
            report['episodes'].append({k: v for k, v in result.items() if k not in ('trace', 'public_history')})
            report['episodes'][-1]['trace_path'] = str(path)
            report['summary'][mode] = summarize(episodes[mode])
            write_json(args.output, report)
            print('%s seed=%s seat=%s status=%s score=%s' %
                  (mode, setting['seed'], setting['focal'], result['status'], result['rewards']), flush=True)
    report['status'] = 'completed' if all(e['status'] == 'completed' for e in report['episodes']) else 'completed_with_errors'
    write_json(args.output, report)


if __name__ == '__main__':
    main()
