"""复盘已执行动作；描述风险信号，不把启发式分歧标作程序错误。"""

from collections import Counter
import json
from pathlib import Path


def diagnose(path, split=None, strategy=None):
    report = json.loads(Path(path).read_text())
    counts = Counter()
    examples = []
    for entry in report['episodes']:
        if split is not None and entry.get('split') != split:
            continue
        if strategy is not None and entry.get('strategy_version') != strategy:
            continue
        episode = json.loads((Path(path).parent / entry['trace_path']).read_text())
        for row in episode['trace']:
            if row['player'] != episode['focal'] or row['status'] != 'applied':
                continue
            view = row['visible_state']; pub = view['public']; action = row['action']['payload']
            if pub['phase'] != 'playing' or len(row['legal_action_ids']) == 1:
                continue
            counts['nonforced_play_decisions'] += 1
            counts['hierarchical_decisions'] += len(row['selection']) > 1
            cards = action['cards']
            if not pub['target']:
                counts['free_leads'] += 1
                if action['kind'] in ('bomb', 'rocket'):
                    counts['bomb_free_leads'] += 1
                    examples.append({'file': entry['trace_path'], 'turn': row['turn'], 'signal': 'bomb_free_lead', 'action': row['action']['id']})
            if pub['owner'] and pub['owner'] == view['private']['teammate']:
                counts['teammate_control_opportunities'] += 1
                counts['teammate_overtakes'] += bool(cards)
            owner_enemy = pub['owner'] and (pub['owner'] == pub['landlord']) != (row['player'] == pub['landlord'])
            if owner_enemy and pub['remaining_counts'][pub['owner']] == 1 and not cards:
                counts['pass_to_one_card_enemy_with_legal_response'] += 1
                examples.append({'file': entry['trace_path'], 'turn': row['turn'], 'signal': 'pass_to_one_card_enemy', 'action': row['action']['id']})
    return {'source': str(path), 'split': split, 'strategy': strategy, 'counts': dict(counts), 'examples': examples,
            'interpretation': 'Descriptive decision contexts, not optimality labels. A legal response does not guarantee blocking all opponents or eventual victory.'}
