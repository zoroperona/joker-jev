"""每款游戏使用独立子目录；显式注册，方便审查加载范围。"""

from .high_card.game import HighCardGame

GAME_REGISTRY = {"high_card": HighCardGame}


def create_game(game_id: str):
    try:
        factory = GAME_REGISTRY[game_id]
    except KeyError as exc:
        raise ValueError("未知游戏: " + game_id) from exc
    return factory()
