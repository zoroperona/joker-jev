# Joker + JEV

用于测试不同卡牌游戏与决策策略的统一环境。每款游戏独立实现规则、信息可见性、合法动作、奖励和记牌推断；共享引擎负责推进对局。Python 3.9+，运行和测试仅使用标准库。

## 当前支持：斗地主

主游戏是**斗地主受限残局**：三人身份、农民团队胜负、记牌和未知牌推断、合法动作、逐轮 JEV 决策及可复盘日志。当前每人剩余 1–4 张，剩余牌池每个普通点数最多两张，支持单牌、对子、王炸。包含手牌数量不均、跟单牌/对子、地主剩一张/两张、一次过牌后的牌权处理。

**尚不支持完整 54 张发牌、叫地主、三带、顺子、连对、飞机、普通炸弹和倍数规则。** `high_card` 仅作为演示如何接入另一款游戏的最小示例。

```bash
# 斗地主：50 副混合残局，轮换三个身份；本地模拟，无需 API key
python3 -m joker_jev.games.doudizhu.fullgame --scenario-set mixed --balanced --cases 50 --seed 20261014 --output reports/my-mixed-local.json
# 加 --live 则在相同设置对比当前 JEV、纯模拟、模拟＋JEV
python3 -m joker_jev.games.doudizhu.fullgame --scenario-set mixed --balanced --cases 50 --seed 20261014 --live --output reports/my-mixed-live.json
```

报告输出路径必须不存在，避免覆盖历史实验。JEV 需要本地 `.env` 配置；模型默认固定为 `jev-1.13.0`。策略选择与人工建议不同，不算测试失败。

## 安装与基础验证

克隆仓库并进入目录即可运行，无额外依赖。以下 `high_card` 命令用于验证通用引擎：

```bash
python3 -m joker_jev --game high_card --seed 42
python3 -m joker_jev --game high_card --seed 42 --episodes 10
python3 -m joker_jev --agent jev --seed 42
python3 -m unittest discover -s tests -v
```

每行输出一局的 JSON，包含动作步数、累计奖励和公开事件。默认使用随机策略。随机基线在相同游戏种子和策略种子下可复现；远程 JEV 的回答不保证可复现。

使用 `--agent jev` 时，首位玩家通过 TypeSafe API 决策，对手使用随机策略。从 `.env.example` 创建本地 `.env`，填写 `TYPESAFE_API_KEY`；endpoint 默认为 `https://api.typesafe.ai/v1/systemone`，模型默认为 `jev-latest`。程序自动读取 `.env`，环境变量优先；`.env` 已被 Git 忽略。运行默认随机对局和测试不需要凭据或网络。

## 分层

```text
joker_jev/
  core/
    models.py          规则、奖励、观察、推断和决策的数据协议
    game.py            CardGame / CardInference 抽象基类
    engine.py          通用对局循环、动作校验、奖励累计
  agents/
    base.py            Agent 抽象基类、随机策略
    jev.py             JEV 的 JSON 输入输出适配器
    typesafe.py        System One HTTP 后端、Choice 和本地配置
  games/
    __init__.py        游戏注册表
    high_card/         双人三轮比牌示例
      game.py          状态、规则、发牌、出牌和结算
      inference.py     已出牌统计、未知牌和对手持牌概率
      agent.py         该游戏专用的启发式基线
      README.md        规则说明与能力边界
docs/
  adding-a-game.md      新游戏必须提供的内容和开发步骤
  jev-protocol.md       JEV 接入约定
```

引擎每一步执行：构造当前玩家观察 → 记牌和推断 → 向 Agent 提供规则与奖励目标 → 验证动作 ID → 执行游戏规则 → 累计奖励与公开历史。

真实完整状态保留在游戏环境内，Agent 和推断器只拿到当前玩家可见信息的副本。推断中的事实、估计和假设分别表达。新增游戏不需要修改引擎。

## 接入决策策略

```python
from joker_jev.agents.base import RandomAgent
from joker_jev.core.engine import play
from joker_jev.games import create_game
from joker_jev.games.high_card.agent import HighCardHeuristicAgent

game = create_game("high_card")
result = play(game, {"p0": HighCardHeuristicAgent(), "p1": RandomAgent(7)}, seed=42)
print(result.rewards)
```

已接入 TypeSafe 的 Jev：`JEVAgent(TypeSafeBackend.from_env())` 将规则、奖惩、可见状态、合法动作、公开历史、推断及自身累计奖励作为 `state`，以合法动作为 `Choice` 候选项。模型返回的选择经校验后交给游戏引擎执行。详见 [接入协议](docs/jev-protocol.md)。

提供规则和奖励能让决策后端据此选择动作，但本框架本身不训练模型，也不保证策略最优。当前支持轮流行动、离散合法动作、合作式本地插件；同时行动需要由游戏先保存私有选择、待结算时再公开。进程内信息隔离不构成不可信代码的安全沙箱。

开发新游戏请遵循 [游戏接入规范](docs/adding-a-game.md)。

## 斗地主策略实验

已加入 10 个小残局，用于测试身份协作、守门、让牌、牌权接管和单双牌控制。JEV 先回答独立战术问题，再选择动作；参考标注与全知底牌不进入模型输入。

```bash
python3 -m joker_jev.games.doudizhu.evaluate
python3 -m joker_jev.games.doudizhu.evaluate --agent jev --output reports/doudizhu-run.json
```

这部分是受限残局评测，还不是完整斗地主。范围、假设和运行方式见 [斗地主策略实验](joker_jev/games/doudizhu/README.md)。

围绕首次“抢队友牌权”的策略差异，另有八例协作对照集，可在不改问题文本的情况下比较显式公开控制事实的作用：

```bash
python3 -m joker_jev.games.doudizhu.compare --repeats 3 --output reports/cooperation-new-run.json
```

还可比较三种首步决策：当前 JEV、纯模拟、模拟加 JEV。模拟只使用玩家视角，枚举兼容隐藏牌并运行有限续局；团队收益、调用成本和诊断参考分别记录。

```bash
# 本地模拟，无 API 调用
python3 -m joker_jev.games.doudizhu.benchmark --output reports/simulation-new-run.json
# 三组真实对照
python3 -m joker_jev.games.doudizhu.benchmark --live --repeats 2 --output reports/three-arm-new-run.json
```

**策略评测没有“必须最优”的通过条件。** 合法性、规则、信息隔离和协议属于正确性测试；人工建议一致性、全知求解和实验团队收益属于诊断与观测指标。

首次三组真实实验已完成，收益、执行超时与成本见 [三组对照报告](reports/doudizhu-three-arm-v1.md)。

每步重新决策的完整残局已接入同一 `CardGame` 引擎，可固定新快照、轮换目标座位，并改变农民搭档风格：

```bash
python3 -m joker_jev.games.doudizhu.fullgame --output reports/full-local-new.json
python3 -m joker_jev.games.doudizhu.fullgame --live --cases 2 --workers 3 --output reports/full-live-new.json
```

每局保存独立逐步记录，网络错误不会伪装成输局；仍限定于小残局，不包含完整发牌和叫地主。详见 [完整残局协议](docs/full-endgame-evaluation.md)。

首轮 36 局全部完成，按身份的结果与一局控制牌路线复盘见 [完整残局报告](reports/doudizhu-fullgame-v1.md)。

扩展评测支持预先均衡分配随机、强压、保守和协作风格。50 副牌 × 三个目标座位 × 三种策略，共 450 局：

```bash
python3 -m joker_jev.games.doudizhu.fullgame --balanced --cases 50 --seed 20261013 --output reports/expanded-local-new.json
python3 -m joker_jev.games.doudizhu.fullgame --balanced --cases 50 --seed 20261013 --live --output reports/expanded-live-new.json
python3 -m joker_jev.games.doudizhu.report reports/expanded-live-new.json --local reports/expanded-local-new.json
```

报告生成器核对本地与线上案例、设置和纯模拟收益一致，汇总收益、成本及实际局面的行为统计。

本轮 50 副牌、450 局已完成：[扩展对照报告](reports/doudizhu-expanded-live-v2.md)。所有局正常结束；本地与线上纯模拟逐设置收益一致。报告同时保留当前 JEV 优于纯模拟的局面，不以最优策略作为通过条件。
