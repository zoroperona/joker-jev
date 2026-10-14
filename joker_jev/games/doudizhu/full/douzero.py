"""Frozen DouZero ADP inference. Only consumes the acting player's observation."""
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from joker_jev.agents.base import Agent
from joker_jev.core.models import Decision
from .agents import FullSimpleAgent
from .cards import DECK, RANKS
from .game import PLAYERS

ENCODING = dict(zip(RANKS, (*range(3, 15), 17, 20, 30)))
POSITIONS = ('landlord', 'landlord_down', 'landlord_up')


def encode(cards):
    return sorted(ENCODING[c] for c in cards)


def infoset(context):
    """No actual opponent hands: their combined pool follows from deck minus seen cards."""
    obs = context.observation
    pub = obs.public
    landlord = PLAYERS.index(pub['landlord'])
    positions = {PLAYERS[(landlord + offset) % 3]: role for offset, role in enumerate(POSITIONS)}
    moves = [e for e in obs.history if e.kind == 'move']
    last = {role: [] for role in POSITIONS}
    for event in moves:
        last[positions[event.data['player']]] = encode(event.data['cards'])
    unseen = Counter(DECK) - Counter(obs.private['hand']) - Counter(
        card for cards in pub['played'].values() for card in cards)
    return SimpleNamespace(
        player_position=positions[obs.player_id], player_hand_cards=encode(obs.private['hand']),
        other_hand_cards=encode(unseen.elements()),  # Aggregate unknown pool, not a hidden allocation.
        legal_actions=[encode(a.payload['cards']) for a in obs.legal_actions],
        last_move=encode(pub['target']['cards']) if pub['target'] else [],
        last_move_dict=last, card_play_action_seq=[encode(e.data['cards']) for e in moves],
        played_cards={positions[p]: encode(cards) for p, cards in pub['played'].items()},
        num_cards_left_dict={positions[p]: n for p, n in pub['remaining_counts'].items()},
        bomb_num=pub['bombs'],
    )


class DouZeroAgent(Agent):
    """CPU inference with pinned pretrained weights; local heuristic only for bidding."""
    def __init__(self, model_dir):
        try:
            import torch
            from douzero.dmc.models import model_dict
            from douzero.env.env import get_obs
        except ImportError as exc:
            raise RuntimeError('请先运行 games/doudizhu/setup.sh 安装 DouZero') from exc
        self.torch, self.get_obs = torch, get_obs
        torch.set_num_threads(1)
        self.models = {}
        for role in POSITIONS:
            path = Path(model_dir) / (role + '.ckpt')
            if not path.is_file():
                raise RuntimeError('缺少 DouZero 权重，请运行 games/doudizhu/setup.sh')
            model = model_dict[role]()
            # Only tensor state dicts are loaded; mismatched/missing tensors are errors.
            model.load_state_dict(torch.load(path, map_location='cpu', weights_only=True), strict=True)
            self.models[role] = model.eval()
        self.bidder = FullSimpleAgent()

    def decide(self, context):
        obs = context.observation
        if obs.public['phase'] == 'bidding':
            choice = self.bidder.decide(context)
            return Decision(choice.action_id, 'fixed_heuristic_bid_v1 (DouZero has no bidding model)')
        if len(obs.legal_actions) == 1:
            return Decision(obs.legal_actions[0].id, '唯一合法动作')
        state = infoset(context)
        encoded = self.get_obs(state)
        torch = self.torch
        # Batch in chunks to keep large airplane attachment sets bounded in memory.
        scores = []
        with torch.inference_mode():
            for start in range(0, len(obs.legal_actions), 128):
                z = torch.from_numpy(encoded['z_batch'][start:start + 128]).float()
                x = torch.from_numpy(encoded['x_batch'][start:start + 128]).float()
                scores.append(self.models[state.player_position](z, x, return_value=True)['values'].flatten())
        values = torch.cat(scores)
        if not torch.isfinite(values).all():
            raise RuntimeError('DouZero 输出了无效评分')
        return Decision(obs.legal_actions[int(values.argmax())].id, 'douzero_ADP_pretrained')
