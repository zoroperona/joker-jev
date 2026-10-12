"""原创、确定性的受限斗地主启发式 AI，不依赖模型或真实对手底牌。"""

from joker_jev.agents.base import Agent
from joker_jev.core.models import Decision
from .environment import strategy_state
from .strategy import RANKS, control_facts


def choose_simple(state):
    actions = state['legal_actions']
    if not actions:
        raise ValueError('没有合法动作')
    if len(actions) == 1:
        return actions[0]['id']
    finishing = [a for a in actions if a['payload']['finishes_own_hand']]
    if finishing:
        return finishing[0]['id']
    plays = [a for a in actions if a['payload']['cards']]
    active = state['public']['active_play']
    counts = state['public']['remaining_counts']
    me = state['self']['seat']
    teammate = state['self']['teammate']
    teams = state['rules']['team']
    enemies = [p for p in counts if teams[p] != teams[me]]
    one_card_enemy = any(counts[p] == 1 for p in enemies)

    def rank(action):
        return RANKS.index(action['payload']['cards'][-1])

    if active['cards']:
        facts = control_facts(state)
        if (facts['active_owner_is_teammate'] and
                not facts['opponent_can_possibly_finish_on_current_play_after_self_pass']):
            return 'pass'
        if one_card_enemy and len(active['cards']) == 1:
            # 危急时用大牌阻断：只是启发式，不知道对方实际剩哪一张。
            return max(plays, key=rank)['id']
    else:
        pairs = [a for a in plays if a['payload']['kind'] == 'pair']
        if one_card_enemy and pairs:
            return min(pairs, key=rank)['id']
        singles = [a for a in plays if a['payload']['kind'] == 'single']
        if teammate == state['self']['next_seat'] and counts.get(teammate) == 1 and singles:
            return min(singles, key=rank)['id']

    # 一般局面先减少剩余出牌轮数，再保对子、节省大牌。
    return min(plays, key=lambda a: (a['payload']['minimum_uncontested_plays'],
                                    a['payload']['breaks_pair'], rank(a)))['id']


class SimpleDoudizhuAgent(Agent):
    def decide(self, context):
        return Decision(choose_simple(strategy_state(context)), 'simple_doudizhu_v1')
