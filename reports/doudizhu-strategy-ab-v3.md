# 完整斗地主策略调整：配对对照

基线 `v2_compact`：v2 consequences with at most 24 final choices and repeated partition lists omitted. JEV still chooses.

候选 `v3`：v2_compact plus player-view sampled playouts (600 play / 200 bid rollouts, simple policy for all seats), candidates ranked by simulated score, immediate finishes played by code, recent history only. JEV still chooses otherwise. 未修改简单 AI 对手。

开发回归集用于复盘；新牌局在评测前冻结且不用于本轮调参。两版本均重新调用同一固定模型，相同初始种子和目标座位；叫分不同可改变最终身份。

冻结 SHA-256：`daf526c87a6dcace8f31502fa6c668fadddd44a0ea163185b7a43555661fde8e`。

| 数据集 | 版本 | 完成/尝试 | 胜/负 | 胜率 | 平均积分 | API 次数 | 已知输入/输出 token |
|---|---|---:|---:|---:|---:|---:|---:|
| development | v2_compact | 10/10 | 5/5 | 50.0% | -0.6 | 79 | 341736/7454 |
| development | v3 | 10/10 | 8/2 | 80.0% | 3.9 | 88 | 355722/11623 |
| fresh | v2_compact | 9/10 | 0/9 | 0.0% | -5.555555555555555 | 78 | 327154/8156 |
| fresh | v3 | 10/10 | 8/2 | 80.0% | 1.5 | 81 | 340772/12226 |

development：两版均完成的配对 10 个，v3 赢/v2_compact 输 3 个，v2_compact 赢/v3 输 0 个。


fresh：两版均完成的配对 9 个，v3 赢/v2_compact 输 8 个，v2_compact 赢/v3 输 0 个。

未完成对局（保留，不计输局）：

- fresh / 20270102 / v2_compact：战术选择返回无效 Choice

## 逐局结果

| 数据集 | 种子 | v2_compact 结果/身份 | v3 结果/身份 |
|---|---:|---|---|
| development | 20261016 | [胜/landlord](doudizhu-strategy-ab-v3-episodes/development-20261016-v2_compact.json) | [胜/landlord](doudizhu-strategy-ab-v3-episodes/development-20261016-v3.json) |
| development | 20261017 | [胜/farmer](doudizhu-strategy-ab-v3-episodes/development-20261017-v2_compact.json) | [胜/landlord](doudizhu-strategy-ab-v3-episodes/development-20261017-v3.json) |
| development | 20261018 | [胜/farmer](doudizhu-strategy-ab-v3-episodes/development-20261018-v2_compact.json) | [胜/farmer](doudizhu-strategy-ab-v3-episodes/development-20261018-v3.json) |
| development | 20261019 | [胜/farmer](doudizhu-strategy-ab-v3-episodes/development-20261019-v2_compact.json) | [胜/farmer](doudizhu-strategy-ab-v3-episodes/development-20261019-v3.json) |
| development | 20261020 | [胜/farmer](doudizhu-strategy-ab-v3-episodes/development-20261020-v2_compact.json) | [胜/farmer](doudizhu-strategy-ab-v3-episodes/development-20261020-v3.json) |
| development | 20261021 | [负/farmer](doudizhu-strategy-ab-v3-episodes/development-20261021-v2_compact.json) | [负/landlord](doudizhu-strategy-ab-v3-episodes/development-20261021-v3.json) |
| development | 20261022 | [负/farmer](doudizhu-strategy-ab-v3-episodes/development-20261022-v2_compact.json) | [胜/landlord](doudizhu-strategy-ab-v3-episodes/development-20261022-v3.json) |
| development | 20261023 | [负/farmer](doudizhu-strategy-ab-v3-episodes/development-20261023-v2_compact.json) | [胜/farmer](doudizhu-strategy-ab-v3-episodes/development-20261023-v3.json) |
| development | 20261024 | [负/farmer](doudizhu-strategy-ab-v3-episodes/development-20261024-v2_compact.json) | [负/farmer](doudizhu-strategy-ab-v3-episodes/development-20261024-v3.json) |
| development | 20261025 | [负/landlord](doudizhu-strategy-ab-v3-episodes/development-20261025-v2_compact.json) | [胜/landlord](doudizhu-strategy-ab-v3-episodes/development-20261025-v3.json) |
| fresh | 20270101 | [负/landlord](doudizhu-strategy-ab-v3-episodes/fresh-20270101-v2_compact.json) | [胜/farmer](doudizhu-strategy-ab-v3-episodes/fresh-20270101-v3.json) |
| fresh | 20270102 | [api_error/未完成](doudizhu-strategy-ab-v3-episodes/fresh-20270102-v2_compact.json) | [负/landlord](doudizhu-strategy-ab-v3-episodes/fresh-20270102-v3.json) |
| fresh | 20270103 | [负/landlord](doudizhu-strategy-ab-v3-episodes/fresh-20270103-v2_compact.json) | [胜/landlord](doudizhu-strategy-ab-v3-episodes/fresh-20270103-v3.json) |
| fresh | 20270104 | [负/farmer](doudizhu-strategy-ab-v3-episodes/fresh-20270104-v2_compact.json) | [胜/farmer](doudizhu-strategy-ab-v3-episodes/fresh-20270104-v3.json) |
| fresh | 20270105 | [负/farmer](doudizhu-strategy-ab-v3-episodes/fresh-20270105-v2_compact.json) | [胜/farmer](doudizhu-strategy-ab-v3-episodes/fresh-20270105-v3.json) |
| fresh | 20270106 | [负/landlord](doudizhu-strategy-ab-v3-episodes/fresh-20270106-v2_compact.json) | [胜/farmer](doudizhu-strategy-ab-v3-episodes/fresh-20270106-v3.json) |
| fresh | 20270107 | [负/farmer](doudizhu-strategy-ab-v3-episodes/fresh-20270107-v2_compact.json) | [胜/farmer](doudizhu-strategy-ab-v3-episodes/fresh-20270107-v3.json) |
| fresh | 20270108 | [负/landlord](doudizhu-strategy-ab-v3-episodes/fresh-20270108-v2_compact.json) | [负/landlord](doudizhu-strategy-ab-v3-episodes/fresh-20270108-v3.json) |
| fresh | 20270109 | [负/landlord](doudizhu-strategy-ab-v3-episodes/fresh-20270109-v2_compact.json) | [胜/landlord](doudizhu-strategy-ab-v3-episodes/fresh-20270109-v3.json) |
| fresh | 20270110 | [负/landlord](doudizhu-strategy-ab-v3-episodes/fresh-20270110-v2_compact.json) | [胜/farmer](doudizhu-strategy-ab-v3-episodes/fresh-20270110-v3.json) |

接口错误和上限不算输局；配对统计只含双方均完成设置。样本很小、对手单一、叫分影响身份，不能据此证明普遍优势或最优性。完整指标和调用记录见 [JSON](doudizhu-strategy-ab-v3.json)。
