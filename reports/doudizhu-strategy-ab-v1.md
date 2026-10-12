# 完整斗地主策略调整：配对对照

v1 为原始 JEV；候选版本 `v2` 增加玩家可见的拆牌方案、动作后果和有条件的牌权规划提示，最终动作仍由 JEV 选择。未修改简单 AI 对手。

开发回归集用于复盘；新牌局在评测前冻结且不用于本轮调参。两版本均重新调用同一固定模型，相同初始种子和目标座位；叫分不同可改变最终身份。

冻结 SHA-256：`c0784eabd9c52a6423b35def56e46218c7e3cad8c28f82c0d01426156949b31b`。

| 数据集 | 版本 | 完成/尝试 | 胜/负 | 胜率 | 平均积分 | API 次数 | 已知输入/输出 token |
|---|---|---:|---:|---:|---:|---:|---:|
| development | v1 | 10/10 | 3/7 | 30.0% | -1.9 | 69 | 274573/14831 |
| development | v2 | 9/10 | 5/4 | 55.6% | 0.6666666666666666 | 64 | 412525/7918 |
| fresh | v1 | 10/10 | 0/10 | 0.0% | -12.4 | 80 | 360918/31317 |
| fresh | v2 | 2/10 | 2/0 | 100.0% | 14.0 | 36 | 180540/3801 |

development：两版均完成的配对 9 个，v2 赢/v1 输 2 个，v1 赢/v2 输 0 个。


fresh：两版均完成的配对 2 个，v2 赢/v1 输 2 个，v1 赢/v2 输 0 个。

未完成对局（保留，不计输局）：

- development / 20261025 / v2：TypeSafe 请求失败，HTTP 400
- fresh / 20261110 / v2：TypeSafe 请求失败，HTTP 400
- fresh / 20261101 / v2：TypeSafe 请求失败，HTTP 400
- fresh / 20261108 / v2：TypeSafe 请求失败，HTTP 400
- fresh / 20261103 / v2：TypeSafe 请求失败，HTTP 400
- fresh / 20261102 / v2：TypeSafe 请求失败，HTTP 400
- fresh / 20261107 / v2：TypeSafe 请求失败，HTTP 400
- fresh / 20261104 / v2：TypeSafe 请求失败，HTTP 400
- fresh / 20261105 / v2：TypeSafe 请求失败，HTTP 400

## 逐局结果

| 数据集 | 种子 | v1 结果/身份 | v2 结果/身份 |
|---|---:|---|---|
| development | 20261016 | [负/landlord](doudizhu-strategy-ab-v1-episodes/development-20261016-v1.json) | [胜/landlord](doudizhu-strategy-ab-v1-episodes/development-20261016-v2.json) |
| development | 20261017 | [负/landlord](doudizhu-strategy-ab-v1-episodes/development-20261017-v1.json) | [胜/farmer](doudizhu-strategy-ab-v1-episodes/development-20261017-v2.json) |
| development | 20261018 | [胜/farmer](doudizhu-strategy-ab-v1-episodes/development-20261018-v1.json) | [胜/farmer](doudizhu-strategy-ab-v1-episodes/development-20261018-v2.json) |
| development | 20261019 | [胜/farmer](doudizhu-strategy-ab-v1-episodes/development-20261019-v1.json) | [胜/farmer](doudizhu-strategy-ab-v1-episodes/development-20261019-v2.json) |
| development | 20261020 | [胜/farmer](doudizhu-strategy-ab-v1-episodes/development-20261020-v1.json) | [胜/farmer](doudizhu-strategy-ab-v1-episodes/development-20261020-v2.json) |
| development | 20261021 | [负/farmer](doudizhu-strategy-ab-v1-episodes/development-20261021-v1.json) | [负/farmer](doudizhu-strategy-ab-v1-episodes/development-20261021-v2.json) |
| development | 20261022 | [负/farmer](doudizhu-strategy-ab-v1-episodes/development-20261022-v1.json) | [负/farmer](doudizhu-strategy-ab-v1-episodes/development-20261022-v2.json) |
| development | 20261023 | [负/landlord](doudizhu-strategy-ab-v1-episodes/development-20261023-v1.json) | [负/farmer](doudizhu-strategy-ab-v1-episodes/development-20261023-v2.json) |
| development | 20261024 | [负/farmer](doudizhu-strategy-ab-v1-episodes/development-20261024-v1.json) | [负/farmer](doudizhu-strategy-ab-v1-episodes/development-20261024-v2.json) |
| development | 20261025 | [负/landlord](doudizhu-strategy-ab-v1-episodes/development-20261025-v1.json) | [api_error/未完成](doudizhu-strategy-ab-v1-episodes/development-20261025-v2.json) |
| fresh | 20261101 | [负/landlord](doudizhu-strategy-ab-v1-episodes/fresh-20261101-v1.json) | [api_error/未完成](doudizhu-strategy-ab-v1-episodes/fresh-20261101-v2.json) |
| fresh | 20261102 | [负/landlord](doudizhu-strategy-ab-v1-episodes/fresh-20261102-v1.json) | [api_error/未完成](doudizhu-strategy-ab-v1-episodes/fresh-20261102-v2.json) |
| fresh | 20261103 | [负/landlord](doudizhu-strategy-ab-v1-episodes/fresh-20261103-v1.json) | [api_error/未完成](doudizhu-strategy-ab-v1-episodes/fresh-20261103-v2.json) |
| fresh | 20261104 | [负/landlord](doudizhu-strategy-ab-v1-episodes/fresh-20261104-v1.json) | [api_error/未完成](doudizhu-strategy-ab-v1-episodes/fresh-20261104-v2.json) |
| fresh | 20261105 | [负/landlord](doudizhu-strategy-ab-v1-episodes/fresh-20261105-v1.json) | [api_error/未完成](doudizhu-strategy-ab-v1-episodes/fresh-20261105-v2.json) |
| fresh | 20261106 | [负/landlord](doudizhu-strategy-ab-v1-episodes/fresh-20261106-v1.json) | [胜/landlord](doudizhu-strategy-ab-v1-episodes/fresh-20261106-v2.json) |
| fresh | 20261107 | [负/landlord](doudizhu-strategy-ab-v1-episodes/fresh-20261107-v1.json) | [api_error/未完成](doudizhu-strategy-ab-v1-episodes/fresh-20261107-v2.json) |
| fresh | 20261108 | [负/landlord](doudizhu-strategy-ab-v1-episodes/fresh-20261108-v1.json) | [api_error/未完成](doudizhu-strategy-ab-v1-episodes/fresh-20261108-v2.json) |
| fresh | 20261109 | [负/landlord](doudizhu-strategy-ab-v1-episodes/fresh-20261109-v1.json) | [胜/landlord](doudizhu-strategy-ab-v1-episodes/fresh-20261109-v2.json) |
| fresh | 20261110 | [负/landlord](doudizhu-strategy-ab-v1-episodes/fresh-20261110-v1.json) | [api_error/未完成](doudizhu-strategy-ab-v1-episodes/fresh-20261110-v2.json) |

接口错误和上限不算输局；配对统计只含双方均完成设置。样本很小、对手单一、叫分影响身份，不能据此证明普遍优势或最优性。完整指标和调用记录见 [JSON](doudizhu-strategy-ab-v1.json)。
