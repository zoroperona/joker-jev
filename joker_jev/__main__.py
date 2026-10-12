import argparse
from dataclasses import asdict
import json

from joker_jev.agents.base import RandomAgent
from joker_jev.games.doudizhu.full.agents import FullSimpleAgent, FullJEVAgent, StrategicJEVAgent, CompactStrategicJEVAgent
from joker_jev.agents.jev import JEVAgent
from joker_jev.agents.typesafe import TypeSafeBackend
from joker_jev.core.engine import play
from joker_jev.games import GAME_REGISTRY, create_game


def main():
    parser = argparse.ArgumentParser(description="运行卡牌对局（默认各方随机策略）")
    parser.add_argument("--game", choices=sorted(GAME_REGISTRY), default="high_card")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--episodes", type=int, default=1)
    parser.add_argument("--agent", choices=("random", "simple", "jev"), default="random",
                        help="random：各方随机；simple：斗地主各方简单 AI；jev：首位 JEV，斗地主其余为简单 AI、其他游戏其余随机")
    parser.add_argument("--strategy", choices=("v1", "v2", "v2_compact"), default="v2_compact", help="完整斗地主 JEV 策略版本")
    parser.add_argument("--env-file", default=".env", help="JEV 的本地配置路径")
    args = parser.parse_args()
    if args.episodes <= 0:
        parser.error("--episodes 必须为正数")
    if args.agent == "simple" and args.game != "doudizhu":
        parser.error("simple 仅用于完整斗地主")
    game = create_game(args.game)
    backend = TypeSafeBackend.from_env(args.env_file) if args.agent == "jev" else None
    for episode in range(args.episodes):
        agents = {p: RandomAgent(10000 + episode * len(game.rules.players) + i)
                  for i, p in enumerate(game.rules.players)}
        if args.game == "doudizhu" and args.agent in ("simple", "jev"):
            agents = {p: FullSimpleAgent() for p in game.rules.players}
        if backend is not None:
            agents[game.rules.players[0]] = {"v1": FullJEVAgent, "v2": StrategicJEVAgent, "v2_compact": CompactStrategicJEVAgent}[args.strategy](backend) if args.game == "doudizhu" else JEVAgent(backend)
        result = play(game, agents, seed=args.seed + episode)
        print(json.dumps(asdict(result), ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
