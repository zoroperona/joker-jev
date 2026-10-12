# 完整斗地主：简单 AI 自对弈

每场从 54 张发牌开始，经过叫地主、底牌公开、完整牌型出牌到自然终局。规则为经典叫分制，含炸弹、王炸、春天/反春天积分。

目标座位轮换 p0/p1/p2，身份由本局叫分决定；其余两位都是简单 AI，包含目标农民的队友。

完成 10/10 场；目标团队 4 胜、6 负，已完成局胜率 **40.0%**；目标平均积分 0.4。
这是 `simple_selfplay` 的结果；自对弈时目标只是记账座位，不是 JEV。

API 尝试 0 次，接口错误 0 次，已知用量 `{}`，未知用量调用 0 次，实际模型 `无 API`。

冻结设置 SHA-256：`e2466f10da6c6024f0dcc333b22ff287a30cb4637eb84e39c57f09624b9b4dce`。不因输赢替换种子，不把接口失败或步数上限当输局。

| 场次 | 种子 | 目标座位 | 最终身份 | 结果 | 积分 | 回合 | 回放 |
|---|---:|---|---|---|---:|---:|---|
| 1 | 20261016 | p0 | landlord | 胜 | 8.0 | 43 | [JSON](doudizhu-full-deal-local-v1-episodes/game_000.json) |
| 2 | 20261017 | p1 | landlord | 负 | -2.0 | 56 | [JSON](doudizhu-full-deal-local-v1-episodes/game_001.json) |
| 3 | 20261018 | p2 | farmer | 胜 | 1.0 | 35 | [JSON](doudizhu-full-deal-local-v1-episodes/game_002.json) |
| 4 | 20261019 | p0 | landlord | 胜 | 2.0 | 43 | [JSON](doudizhu-full-deal-local-v1-episodes/game_003.json) |
| 5 | 20261020 | p1 | farmer | 负 | -4.0 | 58 | [JSON](doudizhu-full-deal-local-v1-episodes/game_004.json) |
| 6 | 20261021 | p2 | landlord | 负 | -2.0 | 26 | [JSON](doudizhu-full-deal-local-v1-episodes/game_005.json) |
| 7 | 20261022 | p0 | landlord | 负 | -2.0 | 44 | [JSON](doudizhu-full-deal-local-v1-episodes/game_006.json) |
| 8 | 20261023 | p1 | landlord | 负 | -2.0 | 47 | [JSON](doudizhu-full-deal-local-v1-episodes/game_007.json) |
| 9 | 20261024 | p2 | farmer | 负 | -1.0 | 22 | [JSON](doudizhu-full-deal-local-v1-episodes/game_008.json) |
| 10 | 20261025 | p0 | landlord | 胜 | 6.0 | 26 | [JSON](doudizhu-full-deal-local-v1-episodes/game_009.json) |

小样本和单一启发式对手不代表普遍实力；身份由叫分产生，也不是随机分组的角色对比。策略不要求最优，胜率不是软件通过门槛。

[完整规则](../docs/full-doudizhu.md) · [原始数据](doudizhu-full-deal-local-v1.json)
