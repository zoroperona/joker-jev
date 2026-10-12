# 斗地主

主游戏现已支持完整经典斗地主，入口为 `full/`，通过 `create_game("doudizhu")` 注册。包含 54 张发牌、叫地主、全套经典牌型、底牌公开、炸弹/春天倍数和终局积分。

```bash
python3 -m joker_jev --game doudizhu --agent simple --seed 42
python3 -m joker_jev.games.doudizhu.full.match --live --episodes 10 --output reports/my-full-games.json
```

[完整规则和实现](../../../docs/full-doudizhu.md) · [完整对局实测](../../../reports/doudizhu-full-deal-live-v1.md)。

## 保留的策略状态与残局回归集

以下文档仅说明历史受限残局模块，用于单独验证身份协作、座位、牌权和出牌路线；它与完整玩法并存。

```bash
# 本地规则检查与参考诊断，无网络调用，无策略通过门槛
python3 -m joker_jev.games.doudizhu.evaluate

# JEV 两阶段战术评测，自动读取 .env
python3 -m joker_jev.games.doudizhu.evaluate --agent jev --output reports/doudizhu-run.json
```

## 策略状态

固定出牌顺序为 `landlord → farmer_after → farmer_before → landlord`：`farmer_after` 是地主下家，`farmer_before` 是地主上家。不用含糊的“离地主近/远”代替实际行动顺序。

| 层次 | 本版提供的内容 |
| --- | --- |
| 确定事实 | 自己手牌、身份、座位、下一位、队友、三方牌数、当前出牌及持有牌权者、连续过牌数、公开已出牌计数 |
| 记牌与推断 | 未知牌池；均匀分配假设下其他玩家持对子、能压住当前牌的概率 |
| 动作特征 | 是否直接出完、是否拆对子、出牌后手牌、无人干扰时最少出牌次数 |
| 战术判断 | 是否需要拦截对手、是否让队友保持牌权、是否给下一位队友送单、是否用对子限制报单对手 |
| 最终目标 | 地主胜则地主 +1、两农民各 -1；任意农民先走则两农民各 +1、地主 -1 |

不为守门、顶牌或自己先走额外奖励；农民共同胜负。`minimum_uncontested_plays` 只评估拆牌，不代表实际剩余回合数。推断按未知实体牌均匀分配，保留相同点数的组合权重，忽略历史策略，因此不宣称是校准后验。

`player_state` 是送入模型的唯一状态来源。它不携带场景名称、人工标注、解释、全知求解结果或其他人的具体手牌。测试要求：交换对手与队友的未知牌、保持自己视角和公开计数不变时，模型输入完全相同。

## 规则范围

采用标准 54 张牌的点数顺序。人工快照每人剩 1 至 4 张牌，整个剩余牌池每个普通点数最多两张、大小王各一张。这个子域只可能出现单牌、对子和王炸，合法动作生成可完整覆盖；超出范围拒绝执行。

响应必须同牌型更大或王炸，可以过牌；两家连续过牌后，领牌者自由出牌。主动领出不能过牌。任何玩家一出完，立即结束，无须等待其他人响应。

这些是人工构造的公开计数快照，不是从一副初始发牌完整重放得到的残局；不提供虚构的叫地主或逐步出牌历史。`played_counts` 包含桌面当前牌。后续完整环境需要生成可重放历史，并覆盖底牌公开等额外知识。

## 第一批场景

| 场景 ID | 检查重点 |
| --- | --- |
| `guard_before_landlord` | 下一位是报单地主时守门，并保留出完路线 |
| `yield_to_teammate` | 队友当前牌安全时，不抢其牌权 |
| `override_yield_to_block` | 同是队友持有牌权，有立即输局风险时接管 |
| `pairs_against_single` | 用对子限制报单地主，保留下一对 |
| `probe_pair_keep_control` | 用小单诱使可能的对子拆牌，保留大单接回 |
| `single_threat_changes_lead` | 面对报单地主要考虑先控牌，不能无条件试探 |
| `feed_next_teammate` | 根据真实行动顺序，让下一位队友先走 |
| `landlord_stop_farmer` | 地主也需要拦截，必要时拆对子夺回牌权 |
| `finish_over_seat_duty` | 农民能直接走完时，共同胜利优先于守门口诀 |
| `single_finish_against_pair` | 地主报双不等于必须打对子，自己能走就走 |

每个场景包含多选参考动作、战术理由和适用假设。`preferred` 是人工标注，模型看不到；不声称这些动作对所有隐藏牌分配都最优。

## JEV 工作流与评测

第一次 API 调用在同一可见状态上并行问四个独立 Noul 战术问题。第二次调用将其作为不确定评估加入状态，使用 Choice 从合法动作中选择。具体规则、牌数、拆牌和出完由代码计算；战术评估不能变成强制规则。只有一个合法动作时不调用服务。

报告保留可见输入、战术问题对应的概率、最终动作及分布、置信度、真实模型版本、token 用量、标注和差异。Noul/Choice 数值不当作实战胜率。可在 `tactics.py` 查看固定问题文本。

另有完整信息 minimax：地主最大化自己的胜负，两农民共同最小化地主胜负。它用于分析参考底牌下的路线，不向模型透露答案，也不要求模型或人工偏好与它一致。其最优解知道所有底牌，**不能作为隐藏信息决策的绝对正确答案**。当前报告中的 `full_information_winning` 只是参考底牌下的诊断。

人工场景匹配率不是实战胜率，也不是独立泛化测试结果。后续先补更多隐藏牌分配和反例，再扩展完整规则、采样推断、基线对手及轮换座位的对局评测。

## 协作策略差异的对照实验

`COOPERATION_SCENARIOS` 单独维护八个协作场景，其中两例来自首次十例，六例新增，首次标注保持不变。覆盖换点数、持大王、交换农民座位、地主已过牌、自己可以直接走完，以及必须王炸接管的反例。

```bash
python3 -m joker_jev.games.doudizhu.compare --repeats 3 --output reports/cooperation-new-run.json
```

默认固定 `jev-1.13.0`，对每个场景分别运行原始状态和增加控制事实的状态，各重复三次。场景与两组先后顺序使用固定种子打乱。两组的战术问题、最终 Choice 问题及合法动作完全一致，唯一差异是 `belief.facts.control`。

新增事实仅从玩家可见信息计算：

- 各玩家在某种兼容的隐藏牌分配下，是否可能压住当前牌或直接出完；既检查点数，也检查牌型及剩余牌数，避免把分属两人的王拼成王炸。
- 自己过牌后、牌权回到原领牌者之前，哪些玩家还有响应机会。
- 这些响应者中，对手是否可能压牌或立即走完。地主之前过牌不证明他没有大牌；若自己过牌会关闭本轮，他此时就不能重新响应。若自己接管、重新出大牌，之前过牌的玩家又能响应。

`False` 表示该事件已被公开信息与规则排除，`True` 仅表示可能，不代表猜中了底牌或一定会发生。事实不强制模型让牌；自己能直接走完时仍保留该动作。

对照程序每次决策后原子保存报告，拒绝覆盖已有报告。HTTP/API 错误单独记录，不计为成功决策；中断前已完成的结果保留。报告含完整问题文本、两组输入、每次决策和模型版本，避免用改写后的提示解释旧结果。

现有十例评测也可显式启用事实：

```bash
python3 -m joker_jev.games.doudizhu.evaluate --agent jev --control-facts --output reports/endgame-with-facts.json
```

默认十例评测继续使用原始状态，方便回归。重复调用和点数变体并非独立样本，不能用这组小实验宣称统计显著或实战胜率提升。

首次对照已完成：两组各 24 次，均有 9 次与人工建议一致，显式控制事实没有改变这组场景中的让牌选择。逐场结果与下一步判断见 [对照报告](../../../reports/doudizhu-cooperation-ab-v1.md)。


## 首步模拟与三组评测

已加入有限续局模拟、当前 JEV、模拟加 JEV 的对照入口：

```bash
python3 -m joker_jev.games.doudizhu.benchmark --live --repeats 2 --output reports/three-arm-new-run.json
```

三组只有首步选择方法不同，后续使用相同的评测策略，记录策略依赖的团队收益与成本。模拟玩家仅使用自己的视角，全知穷举不参与规划。详细边界见 [策略评测规范](../../../docs/strategy-evaluation.md)。

软件测试检查规则和实现；策略与参考建议不同只记录诊断，不判定测试失败。旧原始报告保留历史字段，新报告使用 `human_reference_agreement` 明确其含义。

## 完整残局

`EndgameGame` 已接入通用 `CardGame` 引擎，可运行至自然终局，目标策略每一轮重新决策。支持三个目标座位、协作/贪心两种农民风格、预先固定的新快照、公开历史更新和逐步日志：

```bash
python3 -m joker_jev.games.doudizhu.fullgame --live --output reports/full-new.json
```

这是受限残局的完整对局，不是完整斗地主发牌游戏。范围和配置见 [完整残局协议](../../../docs/full-endgame-evaluation.md)，首轮结果见 [36 局报告](../../../reports/doudizhu-fullgame-v1.md)。
