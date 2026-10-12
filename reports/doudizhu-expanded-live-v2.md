# 50 副固定残局：逐步决策对照

实验状态：`completed`；案例数 50，设置数 150，对局数 450。

案例 SHA-256：`ffc2660cb8c9c8060863c305974163fc5095068112569bc97dbb772ee9ef2197`。

本地与线上 manifest、全部设置以及逐设置纯模拟终局收益完全一致。

## 全部尝试

| 策略 | 完成/尝试 | 胜/负 | 平均团队收益 | API 错误 | API 次数 | 已知输入/输出 token | 平均每局秒 |
|---|---:|---:|---:|---:|---:|---:|---:|
| current_jev | 150/150 | 80/70 | 0.0667 | 0 | 472 | 767775/27309 | 1.924 |
| simulation | 150/150 | 94/56 | 0.2533 | 0 | 0 | 0/0 | 0.100 |
| simulation_jev | 150/150 | 94/56 | 0.2533 | 0 | 251 | 728453/10348 | 1.121 |

收益为团队赢 +1、输 -1；API 错误和步数上限不计输局。耗时含本地计算、网络等待和并发影响；token 是接口返回的已知用量，不代表已核对账单。

三种策略都完成的匹配设置：150。

| 策略 | 匹配设置胜/负 | 匹配平均收益 | 未知用量调用 | 实际模型 |
|---|---:|---:|---:|---|
| current_jev | 80/70 | 0.0667 | 0 | jev-1.13.0 |
| simulation | 94/56 | 0.2533 | 0 | 无 API |
| simulation_jev | 94/56 | 0.2533 | 0 | jev-1.13.0 |

## 按目标座位

| 分组 | 策略 | 完成/尝试 | 胜/负 | 平均收益 |
|---|---|---:|---:|---:|
| landlord | current_jev | 50/50 | 16/34 | -0.36 |
| landlord | simulation | 50/50 | 26/24 | 0.04 |
| landlord | simulation_jev | 50/50 | 26/24 | 0.04 |
| farmer_after | current_jev | 50/50 | 30/20 | 0.2 |
| farmer_after | simulation | 50/50 | 32/18 | 0.28 |
| farmer_after | simulation_jev | 50/50 | 32/18 | 0.28 |
| farmer_before | current_jev | 50/50 | 34/16 | 0.36 |
| farmer_before | simulation | 50/50 | 36/14 | 0.44 |
| farmer_before | simulation_jev | 50/50 | 36/14 | 0.44 |

## 按预先分配风格

| 分组 | 策略 | 完成/尝试 | 胜/负 | 平均收益 |
|---|---|---:|---:|---:|
| conservative | current_jev | 37/37 | 19/18 | 0.027 |
| conservative | simulation | 37/37 | 22/15 | 0.1892 |
| conservative | simulation_jev | 37/37 | 22/15 | 0.1892 |
| cooperative | current_jev | 37/37 | 16/21 | -0.1351 |
| cooperative | simulation | 37/37 | 24/13 | 0.2973 |
| cooperative | simulation_jev | 37/37 | 24/13 | 0.2973 |
| pressure | current_jev | 38/38 | 20/18 | 0.0526 |
| pressure | simulation | 38/38 | 23/15 | 0.2105 |
| pressure | simulation_jev | 38/38 | 23/15 | 0.2105 |
| random | current_jev | 38/38 | 25/13 | 0.3158 |
| random | simulation | 38/38 | 25/13 | 0.3158 |
| random | simulation_jev | 38/38 | 25/13 | 0.3158 |

## 已访问局面的行为描述

下表只统计目标座位已执行的非强制动作；分母是该策略实际访问的局面数量，不是同一批决策机会。因此只能描述行为，不能据此判定哪种策略更正确。

| 策略 | 非强制动作 | 队友掌权时让牌/机会 | 队友掌权时接管/机会 | 对手掌权时接管/机会 | 拆对子 | 出对子 |
|---|---:|---:|---:|---:|---:|---:|
| current_jev | 236 | 0/44 | 44/44 | 84/84 | 3 | 6 |
| simulation | 250 | 5/53 | 48/53 | 99/115 | 6 | 2 |
| simulation_jev | 251 | 9/52 | 43/52 | 88/114 | 2 | 6 |

## 与纯模拟逐设置对照

| 策略 | 同赢 | 同输 | 策略赢/模拟输 | 策略输/模拟赢 |
|---|---:|---:|---:|---:|
| current_jev | 76 | 52 | 4 | 18 |
| simulation_jev | 94 | 56 | 0 | 0 |

终局收益相同不表示出牌路径相同；纯模拟也可能在某些设置输给当前 JEV。所有统计均为本批固定局面的观察，不是最优性证明。

完整匹配设置中，有 22 个设置出现不同终局收益。以下按案例编号列出前 10 个，供复盘，不作为人工正确答案。

| 案例/座位/风格 | current_jev | simulation | simulation_jev |
|---|---:|---:|---:|
| generated_001/landlord/cooperative | [-1.0](doudizhu-expanded-live-v2-episodes/generated_001-landlord-cooperative-0-current_jev.json) | [1.0](doudizhu-expanded-live-v2-episodes/generated_001-landlord-cooperative-0-simulation.json) | [1.0](doudizhu-expanded-live-v2-episodes/generated_001-landlord-cooperative-0-simulation_jev.json) |
| generated_006/farmer_after/cooperative | [-1.0](doudizhu-expanded-live-v2-episodes/generated_006-farmer_after-cooperative-0-current_jev.json) | [1.0](doudizhu-expanded-live-v2-episodes/generated_006-farmer_after-cooperative-0-simulation.json) | [1.0](doudizhu-expanded-live-v2-episodes/generated_006-farmer_after-cooperative-0-simulation_jev.json) |
| generated_012/landlord/random | [-1.0](doudizhu-expanded-live-v2-episodes/generated_012-landlord-random-0-current_jev.json) | [1.0](doudizhu-expanded-live-v2-episodes/generated_012-landlord-random-0-simulation.json) | [1.0](doudizhu-expanded-live-v2-episodes/generated_012-landlord-random-0-simulation_jev.json) |
| generated_015/landlord/pressure | [-1.0](doudizhu-expanded-live-v2-episodes/generated_015-landlord-pressure-0-current_jev.json) | [1.0](doudizhu-expanded-live-v2-episodes/generated_015-landlord-pressure-0-simulation.json) | [1.0](doudizhu-expanded-live-v2-episodes/generated_015-landlord-pressure-0-simulation_jev.json) |
| generated_023/farmer_before/cooperative | [-1.0](doudizhu-expanded-live-v2-episodes/generated_023-farmer_before-cooperative-0-current_jev.json) | [1.0](doudizhu-expanded-live-v2-episodes/generated_023-farmer_before-cooperative-0-simulation.json) | [1.0](doudizhu-expanded-live-v2-episodes/generated_023-farmer_before-cooperative-0-simulation_jev.json) |
| generated_023/landlord/pressure | [-1.0](doudizhu-expanded-live-v2-episodes/generated_023-landlord-pressure-0-current_jev.json) | [1.0](doudizhu-expanded-live-v2-episodes/generated_023-landlord-pressure-0-simulation.json) | [1.0](doudizhu-expanded-live-v2-episodes/generated_023-landlord-pressure-0-simulation_jev.json) |
| generated_026/farmer_after/cooperative | [-1.0](doudizhu-expanded-live-v2-episodes/generated_026-farmer_after-cooperative-0-current_jev.json) | [1.0](doudizhu-expanded-live-v2-episodes/generated_026-farmer_after-cooperative-0-simulation.json) | [1.0](doudizhu-expanded-live-v2-episodes/generated_026-farmer_after-cooperative-0-simulation_jev.json) |
| generated_026/landlord/conservative | [-1.0](doudizhu-expanded-live-v2-episodes/generated_026-landlord-conservative-0-current_jev.json) | [1.0](doudizhu-expanded-live-v2-episodes/generated_026-landlord-conservative-0-simulation.json) | [1.0](doudizhu-expanded-live-v2-episodes/generated_026-landlord-conservative-0-simulation_jev.json) |
| generated_029/farmer_before/pressure | [1.0](doudizhu-expanded-live-v2-episodes/generated_029-farmer_before-pressure-0-current_jev.json) | [-1.0](doudizhu-expanded-live-v2-episodes/generated_029-farmer_before-pressure-0-simulation.json) | [-1.0](doudizhu-expanded-live-v2-episodes/generated_029-farmer_before-pressure-0-simulation_jev.json) |
| generated_029/landlord/cooperative | [-1.0](doudizhu-expanded-live-v2-episodes/generated_029-landlord-cooperative-0-current_jev.json) | [1.0](doudizhu-expanded-live-v2-episodes/generated_029-landlord-cooperative-0-simulation.json) | [1.0](doudizhu-expanded-live-v2-episodes/generated_029-landlord-cooperative-0-simulation_jev.json) |

## 适用范围

每人三张的合成残局，仅有单牌、对子和王炸，不含完整发牌、叫地主、顺子或倍数规则。三个座位来自同一副牌；均衡模式的风格分配并非全交叉。不能把全部对局视作独立样本，也不能从分组胜率推断风格的因果效果。

结果不要求 JEV 最优，不使用人工动作标签或全知解筛选案例。错误、策略收益、调用用量分别记录。查看结果后，这批案例成为开发数据；后续改动应另取新样本验证。

原始记录：[doudizhu-expanded-live-v2.json](doudizhu-expanded-live-v2.json)；[协议](../docs/full-endgame-evaluation.md)。
