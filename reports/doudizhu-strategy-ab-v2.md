# 完整斗地主策略调整：配对对照

v1 为原始 JEV；候选版本 `v2_compact` 增加玩家可见的拆牌方案、动作后果和有条件的牌权规划提示，最终动作仍由 JEV 选择。未修改简单 AI 对手。

开发回归集用于复盘；新牌局在评测前冻结且不用于本轮调参。两版本均重新调用同一固定模型，相同初始种子和目标座位；叫分不同可改变最终身份。

冻结 SHA-256：`f7e2e710ddca0b3e207184dfc4fa10bac17c262265850790bffb994c8acfe29a`。

| 数据集 | 版本 | 完成/尝试 | 胜/负 | 胜率 | 平均积分 | API 次数 | 已知输入/输出 token |
|---|---|---:|---:|---:|---:|---:|---:|
| development | v1 | 10/10 | 4/6 | 40.0% | -1.6 | 72 | 293938/17000 |
| development | v2_compact | 10/10 | 5/5 | 50.0% | -0.6 | 80 | 342973/7392 |
| fresh | v1 | 9/10 | 0/9 | 0.0% | -7.222222222222222 | 82 | 338731/23853 |
| fresh | v2_compact | 9/10 | 3/6 | 33.3% | -1.6666666666666667 | 94 | 401933/10634 |

development：两版均完成的配对 10 个，v2 赢/v1 输 1 个，v1 赢/v2 输 0 个。


fresh：两版均完成的配对 8 个，v2 赢/v1 输 3 个，v1 赢/v2 输 0 个。

未完成对局（保留，不计输局）：

- fresh / 20261210 / v2_compact：战术选择返回无效 Choice
- fresh / 20261205 / v1：战术选择返回无效 Choice

## 逐局结果

| 数据集 | 种子 | v1 结果/身份 | v2_compact 结果/身份 |
|---|---:|---|---|
| development | 20261016 | [负/landlord](doudizhu-strategy-ab-v2-episodes/development-20261016-v1.json) | [胜/landlord](doudizhu-strategy-ab-v2-episodes/development-20261016-v2_compact.json) |
| development | 20261017 | [胜/farmer](doudizhu-strategy-ab-v2-episodes/development-20261017-v1.json) | [胜/farmer](doudizhu-strategy-ab-v2-episodes/development-20261017-v2_compact.json) |
| development | 20261018 | [胜/farmer](doudizhu-strategy-ab-v2-episodes/development-20261018-v1.json) | [胜/farmer](doudizhu-strategy-ab-v2-episodes/development-20261018-v2_compact.json) |
| development | 20261019 | [胜/farmer](doudizhu-strategy-ab-v2-episodes/development-20261019-v1.json) | [胜/farmer](doudizhu-strategy-ab-v2-episodes/development-20261019-v2_compact.json) |
| development | 20261020 | [胜/farmer](doudizhu-strategy-ab-v2-episodes/development-20261020-v1.json) | [胜/farmer](doudizhu-strategy-ab-v2-episodes/development-20261020-v2_compact.json) |
| development | 20261021 | [负/farmer](doudizhu-strategy-ab-v2-episodes/development-20261021-v1.json) | [负/farmer](doudizhu-strategy-ab-v2-episodes/development-20261021-v2_compact.json) |
| development | 20261022 | [负/farmer](doudizhu-strategy-ab-v2-episodes/development-20261022-v1.json) | [负/farmer](doudizhu-strategy-ab-v2-episodes/development-20261022-v2_compact.json) |
| development | 20261023 | [负/landlord](doudizhu-strategy-ab-v2-episodes/development-20261023-v1.json) | [负/farmer](doudizhu-strategy-ab-v2-episodes/development-20261023-v2_compact.json) |
| development | 20261024 | [负/farmer](doudizhu-strategy-ab-v2-episodes/development-20261024-v1.json) | [负/farmer](doudizhu-strategy-ab-v2-episodes/development-20261024-v2_compact.json) |
| development | 20261025 | [负/landlord](doudizhu-strategy-ab-v2-episodes/development-20261025-v1.json) | [负/landlord](doudizhu-strategy-ab-v2-episodes/development-20261025-v2_compact.json) |
| fresh | 20261201 | [负/landlord](doudizhu-strategy-ab-v2-episodes/fresh-20261201-v1.json) | [胜/landlord](doudizhu-strategy-ab-v2-episodes/fresh-20261201-v2_compact.json) |
| fresh | 20261202 | [负/landlord](doudizhu-strategy-ab-v2-episodes/fresh-20261202-v1.json) | [负/landlord](doudizhu-strategy-ab-v2-episodes/fresh-20261202-v2_compact.json) |
| fresh | 20261203 | [负/landlord](doudizhu-strategy-ab-v2-episodes/fresh-20261203-v1.json) | [胜/landlord](doudizhu-strategy-ab-v2-episodes/fresh-20261203-v2_compact.json) |
| fresh | 20261204 | [负/landlord](doudizhu-strategy-ab-v2-episodes/fresh-20261204-v1.json) | [负/landlord](doudizhu-strategy-ab-v2-episodes/fresh-20261204-v2_compact.json) |
| fresh | 20261205 | [api_error/未完成](doudizhu-strategy-ab-v2-episodes/fresh-20261205-v1.json) | [负/landlord](doudizhu-strategy-ab-v2-episodes/fresh-20261205-v2_compact.json) |
| fresh | 20261206 | [负/landlord](doudizhu-strategy-ab-v2-episodes/fresh-20261206-v1.json) | [负/landlord](doudizhu-strategy-ab-v2-episodes/fresh-20261206-v2_compact.json) |
| fresh | 20261207 | [负/farmer](doudizhu-strategy-ab-v2-episodes/fresh-20261207-v1.json) | [负/farmer](doudizhu-strategy-ab-v2-episodes/fresh-20261207-v2_compact.json) |
| fresh | 20261208 | [负/farmer](doudizhu-strategy-ab-v2-episodes/fresh-20261208-v1.json) | [胜/farmer](doudizhu-strategy-ab-v2-episodes/fresh-20261208-v2_compact.json) |
| fresh | 20261209 | [负/landlord](doudizhu-strategy-ab-v2-episodes/fresh-20261209-v1.json) | [负/landlord](doudizhu-strategy-ab-v2-episodes/fresh-20261209-v2_compact.json) |
| fresh | 20261210 | [负/landlord](doudizhu-strategy-ab-v2-episodes/fresh-20261210-v1.json) | [api_error/未完成](doudizhu-strategy-ab-v2-episodes/fresh-20261210-v2_compact.json) |

接口错误和上限不算输局；配对统计只含双方均完成设置。样本很小、对手单一、叫分影响身份，不能据此证明普遍优势或最优性。完整指标和调用记录见 [JSON](doudizhu-strategy-ab-v2.json)。
