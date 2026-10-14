"""Frozen DouZero weights, independent of the table server and its action list."""
from pathlib import Path
from .state import ROLES


class DouZeroPolicy:
    def __init__(self, model_dir):
        import torch
        from douzero.dmc.models import model_dict
        from douzero.env.env import get_obs
        self.torch, self.get_obs = torch, get_obs
        torch.set_num_threads(1)
        self.models = {}
        for role in ROLES:
            model = model_dict[role]()
            model.load_state_dict(torch.load(Path(model_dir) / (role + '.ckpt'),
                                            map_location='cpu', weights_only=True), strict=True)
            self.models[role] = model.eval()

    def choose(self, state):
        actions = state.actions()
        info = state.infoset()
        observation = self.get_obs(info)
        scores = []
        with self.torch.inference_mode():
            for start in range(0, len(actions), 128):
                z = self.torch.from_numpy(observation['z_batch'][start:start + 128]).float()
                x = self.torch.from_numpy(observation['x_batch'][start:start + 128]).float()
                scores.append(self.models[info.player_position](z, x, return_value=True)['values'].flatten())
        values = self.torch.cat(scores)
        if not self.torch.isfinite(values).all():
            raise ValueError('Invalid model scores')
        return actions[int(values.argmax())]
