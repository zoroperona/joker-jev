# Joker + JEV

> 新开发方向：截图驱动的独立斗地主客户端，DouZero 权重负责策略，Jev 只做 UI 操作映射。见 [外部工具架构与启动](docs/external-player.md)。原有策略实验保留。图片模式的公开模型、自建服务和硬件要求见 [视觉后端部署](docs/vision-backends.md)。

[English](README.md) | 中文

用于测试卡牌游戏与 JEV 决策的可扩展 Python 框架。**当前主游戏支持完整的三人经典斗地主**：从 54 张发牌、叫地主、公开底牌到完整牌型出牌和终局计分。Python 3.9+，仅依赖标准库。

## 快速开始

```bash
git clone https://github.com/zoroperona/joker-jev.git
cd joker-jev
# 完整斗地主，三位简单 AI 自对弈，无需密钥
python3 -m joker_jev --game doudizhu --agent simple --seed 42
# 完整对局 10 场，保存汇总、逐步回放和 Markdown 报告
python3 -m joker_jev.games.doudizhu.full.match --episodes 10 --output reports/my-full-local.json
# 正确性测试
python3 -m unittest discover -s tests -v
```

使用 JEV 时，将 `.env.example` 复制为本地 `.env` 并填写 `TYPESAFE_API_KEY`。默认 endpoint 为 `https://api.typesafe.ai/v1/systemone`；实验模型固定为 `jev-1.13.0`。`.env` 被 Git 忽略，不要把密钥写进报告或提交。

```bash
# 10 场真实完整对局：JEV 控制一个轮换座位，其余两位为简单 AI
python3 -m joker_jev.games.doudizhu.full.match --live --episodes 10 --seed 20261016 --output reports/my-full-live.json
```

输出路径必须不存在，避免覆盖历史结果。JEV 身份由每局叫分决定；当它是农民时，队友也是简单 AI。远程输出不保证重跑完全一致；不因输赢重抽牌局，接口错误单列且不算输局。

## 完整玩法

- 54 张牌，17/17/17 张加 3 张底牌；1–3 分叫地主，全不叫重发，地主先出。
- 单张、对子、三张、三带一/对、顺子、连对、飞机及单/对翅、四带二单/二对、炸弹、王炸。
- 两家过牌归还牌权；地主对两位农民，农民共享胜负。
- 炸弹/王炸翻倍，春天/反春天翻倍；地主与农民按 2:1:1 积分，零和结算。
- 自身手牌隔离、公开记牌、底牌约束与未知牌估计、逐轮重新决策和日志。

采用经典叫分制，不启用额外抢地主、加倍、癞子或四人变体；飞机单翅、四带二等地区差异已明确约定。详见 [完整规则和实现](docs/full-doudizhu.md)。

## AI 与 JEV

完整玩法的 `FullSimpleAgent` 是原创启发式 AI：评估手牌叫分，出完优先、队友让牌、报单守门、保留炸弹，并用近似剩余组合数选牌。不使用模型、训练权重或真实对手底牌。

JEV 接收规则、奖惩、自己手牌、公开状态、推断与合法选项，返回 Choice。命令行当前默认使用 `v3`：在 `v2_compact` 基础上，为每个候选附加玩家视角的隐藏牌采样模拟（团队胜率、平均积分、样本数），按模拟积分排序，候选通常一次 Choice 选完；能立即出完时由代码直接出完。详见 [v3 采样模拟](docs/simulation-strategy.md)。`v2_compact` 为：补充自己的拆牌方案、每个动作后的剩余组合数、控制牌消耗与过牌后果。最终动作选择每组最多 24 项；候选较多时分层选择牌型、主体及附件分组，保留全部合法候选。JEV 仍决定最终动作，不手工覆盖其合法选择；拆牌组数不是胜率，返回概率也不是实际获胜概率。

**策略不要求最优。** 合法性、规则、信息隔离和协议属于正确性测试；胜率、积分、耗时、调用用量是表现指标。与人工建议不同不等于测试失败。

## 策略调整与最新对照

**最新（v3 采样模拟）**：与 v2_compact 在同一 20 副牌上配对重跑（`jev-1.13.0`），v3 胜 16/20（80%），v2_compact 胜 5/19；双方完成的 19 对中 v3 独赢 11 对、v2_compact 独赢 0 对。新牌 10 副上 v3 8/10、v2_compact 0/9。v3 不再出现需两次调用的决策，每局耗时 7.9 s → 12.8 s（本地模拟）。小样本、对手与模拟策略相同，详见 [v3 说明](docs/simulation-strategy.md) 与 [配对报告](reports/doudizhu-strategy-ab-v3.md)。

线上配对（`jev-1.13.0`，开发回归 10 副 + 新牌 10 副，20270101 起，每副两版各跑一次）：

| 数据集 | v2_compact 胜/完成 | v3 胜/完成 | v2_compact 平均积分 | v3 平均积分 |
|---|---:|---:|---:|---:|
| 开发回归 | 5/10 | **8/10** | -0.6 | 3.9 |
| 新牌 | 0/9 | **8/10** | -5.6 | 1.5 |

v2_compact 有 1 局 Choice 响应校验失败，保留为未完成、不计输局；v3 无失败。

| 速度与用量 | v2_compact | v3 |
|---|---:|---:|
| 每局 API 调用 | 7.8 | 8.4（立即出完不再调用；叫分更常有多个选项） |
| 需要两次调用的决策 | 10/146 | 0/174 |
| 平均输入 token / 调用 | 4260 | 4121 |
| 每局耗时 | 7.9 s | 12.8 s |

耗时增加来自本地模拟；评测用 3 个线程并行，CPU 模拟受 GIL 争用，单局串行时增加量约为每个决策 0.5 s。JEV 在 149 次有模拟的决策里有 126 次（85%）选择了模拟排名第一的动作。

离线验证（免 API，同一 600 副牌，对手为简单 AI，`full/local_eval.py`）：

| 目标座位策略 | 胜率 | 平均积分 |
|---|---:|---:|
| simple（基线） | 51.8% | -0.05 |
| rollout_play（只改出牌） | 73.7% | +2.04 |
| rollout（叫分+出牌） | 69.0% | +2.41 |

以下为此前 v1 与 v2_compact 的对照：

复盘原版发现开局领炸弹、提前用完控制牌、拆散后续组合、对手报单时仍过牌等需要评估的行为。新版增加可见后果和出牌顺序提示；这些是条件性考虑，不是强制“正确答案”。详见 [原因分析与调整说明](docs/strategy-adjustment.md)。

两版在同一模型、同一初始牌局和目标座位上重新运行。**只比较双方均完成的配对**：

| 数据集 | 完整配对 | 原版 v1 胜率 | 新版 v2_compact 胜率 |
|---|---:|---:|---:|
| 原 10 副牌（开发回归） | 10 | 4/10，40% | 5/10，50% |
| 另一批新牌 | 8 | 0/8，0% | 3/8，37.5% |

最新共尝试 40 局，38 局完成。新牌中两版各有 1 局 Choice 响应校验失败，发生在不同设置，保留为未完成，不计输局、不自动补跑。修订版未再发生请求超长。早期较大的特征请求曾触发 `max_tokens_exceeded`，失败结果也保留在报告中。

[最新配对报告与逐局记录](reports/doudizhu-strategy-ab-v2.md) · [行为统计](reports/doudizhu-strategy-ab-v2-behavior.json) · [早期含失败请求的报告](reports/doudizhu-strategy-ab-v1.md)。这是一组小样本观察，不能证明稳定实力提升；叫分会改变地主身份，收益变化也不能全归因于出牌。

```bash
# v3 采样模拟（命令行默认版本）
python3 -m joker_jev.games.doudizhu.full.match --live --strategy v3 --episodes 10 --output reports/my-v3.json
# v2_compact
python3 -m joker_jev.games.doudizhu.full.match --live --strategy v2_compact --episodes 10 --output reports/my-improved.json
# 免 API 离线配对评测：simple / rollout_play / rollout
python3 -m joker_jev.games.doudizhu.full.local_eval --games 600 --strategies simple,rollout_play,rollout --workers 8
# 保留原版，用于对照
python3 -m joker_jev.games.doudizhu.full.match --live --strategy v1 --episodes 10 --output reports/my-original.json
# 复现已发布的配对设置；这批牌已被观察，重跑不再是新的留出验证
python3 -m joker_jev.games.doudizhu.full.compare_strategies --baseline v1 --candidate v2_compact --fresh-seed 20261201 --output reports/my-comparison.json
```

### 策略仍可完善

当前没有达到最优打法，也没有完成大规模实力验证。已完成（v3，见 [采样模拟说明](docs/simulation-strategy.md)）：

- ~~分开评测叫地主与出牌策略~~：离线 600 局消融，仅出牌用模拟胜率 51.8% → 73.7%；叫分也用模拟时平均积分最高（+2.41）。
- ~~有限步的隐藏牌采样和后续对局模拟~~：`full/rollout.py`，约 0.5 s / 决策。
- ~~守门、送牌、接管牌权与身份、位置结合~~：由模拟按真实轮次打完体现，不再加固定口诀。

后续重点：

- 模拟中所有座位使用简单 AI 打法，正好等于当前对手；需加入不同风格对手，检验对手模型不匹配时的收益。
- 改进基于公开行为的猜牌，保留不确定性，不把过牌认定为没有大牌。
- 使用更多未见牌局、多种对手及重复运行，联合统计胜率、积分、完成率和调用成本。
- 继续完善响应校验诊断、请求大小控制；不把失败请求隐藏成随机代打。

## 完整对局实测

首轮 **10 场真实 JEV 对简单 AI** 全部正常结束：JEV 团队 **3 胜 7 负，胜率 30%**，平均积分 -1.9，0 接口错误。固定种子 20261016–20261025，实际模型 `jev-1.13.0`，共 69 次 API 调用，已知输入 269,793 / 输出 16,021 token。

| JEV 最终身份 | 场数 | 胜/负 |
|---|---:|---:|
| 地主 | 4 | 0/4 |
| 农民 | 6 | 3/3 |

身份由叫分产生；10 场和一种简单对手不足以推断稳定实力。原先残局实验的 50% 不是完整对局胜率。

[完整对局报告与逐场回放](reports/doudizhu-full-deal-live-v1.md) · [原始数据](reports/doudizhu-full-deal-live-v1.json) · [本地完整自对弈](reports/doudizhu-full-deal-local-v1.md)。

正确性测试包括完整玩法与原有残局回归，当前 **91 项通过**。完整玩法测试见 [test_full_doudizhu.py](tests/test_full_doudizhu.py)。

## 架构与扩展

```text
joker_jev/
  core/                    CardGame、Agent 上下文、共享对局引擎和奖励协议
  agents/                  通用随机/JEV 策略、TypeSafe HTTP 后端
  games/
    doudizhu/
      full/                完整牌型、发牌/叫分/出牌状态机、AI 和完整对局评测
      environment.py       保留的受限残局环境
      strategy.py          保留的残局推断与离线诊断
    high_card/             最小比牌示例，演示第二款游戏接入
```

每个游戏独立提供规则、状态、合法动作、观察、奖励和推断；共享引擎检查合法性、推进状态并累计奖励。完整斗地主通过 `create_game("doudizhu")` 注册；小残局用固定快照构造 `EndgameGame`。

[游戏接入规范](docs/adding-a-game.md) · [JEV 协议](docs/jev-protocol.md) · [策略评测原则](docs/strategy-evaluation.md)。进程内视角隔离用于可信插件，不是运行恶意插件的安全沙箱。

## 保留的残局实验

原有受限残局、模拟评分与三策略对照均保留，可单独复现：

```bash
python3 -m joker_jev.games.doudizhu.fullgame --scenario-set mixed --balanced --cases 50 --seed 20261014 --output reports/my-endgames.json
python3 -m joker_jev.games.doudizhu.match --seed 20261015 --output reports/my-endgame-jev.json
```

这些旧实验每人只剩 1–4 张，不能当作完整对局结果：

- [50 副固定残局、450 局三策略对照](reports/doudizhu-expanded-live-v2.md)：当前 JEV 80/150 胜，纯模拟和模拟＋JEV 各 94/150 胜。
- [10 场受限残局 JEV 对简单 AI](reports/jev-vs-simple-10-v1.md)：5 胜 5 负，胜率 50%。
- [残局协议](docs/full-endgame-evaluation.md) · [残局 AI 设计](docs/simple-doudizhu-ai.md)。

## 配置与公开数据

仓库只提供不含密钥的 `.env.example`；真实 `.env` 留在本地并被忽略。已发布回放来自合成发牌，不包含真实玩家身份或账户信息；研究日志包含各座位在各自回合的手牌，以便复盘，不会传给其他 Agent。不要将自己的 API key、请求鉴权头或真实用户资料写入日志、Issue 或提交。
