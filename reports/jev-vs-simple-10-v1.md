# 10 场：JEV 对简单斗地主 AI

当前支持受限残局，不是完整 54 张斗地主。目标策略轮换座位，另外两个座位使用原创 `simple_doudizhu_v1`；当目标是农民时，队友也是简单 AI。

本次目标策略：`current_jev`。

完成 10/10 场，目标团队 5 胜、5 负，已完成局胜率 **50.0%**。

API 调用 22 次，接口错误 0 次，已知用量 `{'input_tokens': 34754, 'output_tokens': 1246}`，未知用量调用 0 次，实际模型 `jev-1.13.0`。

## 固定协议

- 种子 `20261015`；10 副牌在调用前固定，SHA-256 `7d0a1a5b47336cce68857f70723b6c25904497b2c7c3dd837ce81575c7555f50`。
- 五个结构层各 2 副：手牌不均、跟单牌、跟对子、地主一张、地主两张。
- 地主 4 场，地主下家 3 场，地主上家 3 场；不按胜负或动作筛选。
- 接口错误和步数上限保留为未完成，不算输局，不自动重试。
- AI 只看自己的手牌及公开信息；没有实际对手底牌、全知求解或 JEV 调用。

| 场次 | 情况 | 目标身份 | 结果 | 回放 |
|---|---|---|---|---|
| 1 | uneven_lead | landlord | 胜 | [JSON](jev-vs-simple-10-v1-episodes/mixed_000.json) |
| 2 | respond_single | farmer_after | 负 | [JSON](jev-vs-simple-10-v1-episodes/mixed_001.json) |
| 3 | respond_pair | farmer_before | 胜 | [JSON](jev-vs-simple-10-v1-episodes/mixed_002.json) |
| 4 | landlord_one | landlord | 胜 | [JSON](jev-vs-simple-10-v1-episodes/mixed_003.json) |
| 5 | landlord_two | farmer_after | 负 | [JSON](jev-vs-simple-10-v1-episodes/mixed_004.json) |
| 6 | uneven_lead | farmer_before | 负 | [JSON](jev-vs-simple-10-v1-episodes/mixed_005.json) |
| 7 | respond_single | landlord | 负 | [JSON](jev-vs-simple-10-v1-episodes/mixed_006.json) |
| 8 | respond_pair | farmer_after | 胜 | [JSON](jev-vs-simple-10-v1-episodes/mixed_007.json) |
| 9 | landlord_one | farmer_before | 负 | [JSON](jev-vs-simple-10-v1-episodes/mixed_008.json) |
| 10 | landlord_two | landlord | 胜 | [JSON](jev-vs-simple-10-v1-episodes/mixed_009.json) |

只有 10 场，且身份和局面难度不相同；这是可复现的协议与对局演示，不是稳定实力估计。远程模型输出可能随时间变化。胜率不能用于判定软件测试是否通过。

[原始数据](jev-vs-simple-10-v1.json) · [AI 设计](../docs/simple-doudizhu-ai.md)
