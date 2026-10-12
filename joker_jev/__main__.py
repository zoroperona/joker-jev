import argparse
from dataclasses import asdict
import json

from joker_jev.agents.base import RandomAgent
from joker_jev.agents.jev import JEVAgent
from joker_jev.agents.typesafe import TypeSafeBackend
from joker_jev.core.engine import play
from joker_jev.games import GAME_REGISTRY, create_game


def main():
    parser = argparse.ArgumentParser(description="运行卡牌测试对局（默认双方随机策略）")
    parser.add_argument("--game", choices=sorted(GAME_REGISTRY), default="high_card")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--episodes", type=int, default=1)
    parser.add_argument("--agent", choices=("random", "jev"), default="random",
                        help="首位玩家的策略，其他玩家使用随机策略")
    parser.add_argument("--env-file", default=".env", help="JEV 的本地配置路径")
    args = parser.parse_args()
    if args.episodes <= 0:
        parser.error("--episodes 必须为正数")
    game = create_game(args.game)
    backend = TypeSafeBackend.from_env(args.env_file) if args.agent == "jev" else None
    for episode in range(args.episodes):
        agents = {p: RandomAgent(10000 + episode * len(game.rules.players) + i)
                  for i, p in enumerate(game.rules.players)}
        if backend is not None:
            agents[game.rules.players[0]] = JEVAgent(backend)
        result = play(game, agents, seed=args.seed + episode)
        print(json.dumps(asdict(result), ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
