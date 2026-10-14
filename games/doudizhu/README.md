# 三人局 · 斗地主网页版

固定对手现使用 **已有 DouZero ADP 预训练模型**，不训练。支持手动出牌、DouZero 自对局、JEV 精简／辅助信息两种对局。

## 安装与启动

首次准备（需 [uv](https://docs.astral.sh/uv/getting-started/installation/)，脚本创建独立 Python 3.11 环境、安装 CPU 推理依赖、下载并校验三个模型）：

```sh
bash games/doudizhu/setup.sh
bash games/doudizhu/start.sh --port 8877
```

打开 http://127.0.0.1:8877。默认你手动操作，另外两席使用同一套冻结的 DouZero 模型。关闭网页不停止自动对局，Ctrl+C 停止服务器。

JEV 使用仓库根目录 `.env` 中现有 `TYPESAFE_API_KEY`、`TYPESAFE_API_URL`、`TYPESAFE_MODEL`；密钥只在服务器使用，不会发给网页。配置后重启服务，页面中选择「JEV 决策」及信息模式，再点「应用并开始新局」。这会调用 JEV API、产生用量。**切换配置会重开牌局并清零累计积分**，避免一局混用两个策略。

直接启动自动模式：

```sh
# 全部座位用 DouZero，完全本地推理
bash games/doudizhu/start.sh --port 8877 --controller douzero

# p0 为 JEV，p1/p2 固定为 DouZero
bash games/doudizhu/start.sh --port 8877 --controller jev --jev-mode minimal
bash games/doudizhu/start.sh --port 8877 --controller jev --jev-mode assisted
```

仍可从另一终端控制运行中的牌桌（使用同一端口）：

```sh
python3 games/doudizhu/autoplay.py --port 8877 --delay 0.9
python3 games/doudizhu/autoplay.py --port 8877 --off
```

手动模式开启托管后 p0 使用 DouZero；JEV 模式开启托管后 p0 使用选定的 JEV 模式。结算停留 4 秒后自动开始新局。「接管牌局」关闭自动操作；已发出的 API 请求无法撤销，但返回的旧决策不会落到已接管或重开的牌局中。出错会暂停并显示重试按钮，不会偷偷降级成简单 AI。

## JEV 信息模式

| 输入／行为 | 精简 `minimal` | 辅助 `assisted` |
|---|---|---|
| 规则、计分、身份与座位 | 有 | 相同 |
| 自己手牌、公开底牌、剩余张数、桌面牌 | 有 | 相同 |
| 完整公开历史、全部合法动作 | 有 | 相同 |
| 未知牌池推断及期望张数 | 无 | 有（不是对手真实手牌） |
| 拆牌组数、动作后果、可见控制事实 | 无 | 有 |
| 模拟胜率／模拟排序 | 无 | 无 |
| 强制让牌／直接出完捷径 | 无 | 无 |

两种模式共用目标指令、动作顺序和分组选牌流程；候选超过 24 时使用相同分层，保留全部合法动作。只有唯一合法动作时由代码直接执行。每个候选不重复发送完整残余手牌或拆牌列表，以控制请求大小。辅助模式不等同于历史 `v3`：本次有意不混入模拟排名和动作捷径，只比较补充信息的影响。

## 配对对照：固定模型、同种子与同座位

```sh
games/doudizhu/.venv/bin/python games/doudizhu/compare.py \
  --input-mode both --episodes 3 --seed 42 \
  --model jev-1.13.0 --output games/doudizhu/runs/my-comparison.json
```

每种模式各 3 局，共 6 局。目标座位轮换 p0/p1/p2；其余两席始终为同一冻结 DouZero，目标为农民时也包含其队友。两组共享初始发牌与目标座位，模式执行顺序交替；身份仍由叫分决定，后续局面可能分叉。`--input-mode minimal` / `assisted` 可单独跑一组。

输出包含权重 SHA-256、种子／座位、两组积分与团队胜负、API 用量、错误状态和逐步记录。逐局 `sent_requests` 才是实际送给 JEV 的输入；通用 `visible_state` 记录的是引擎上下文，可能包含精简模式未发送的推断。API 失败不算输局，拒绝覆盖已有报告。小样本验证不代表哪种模式实力更强。

网页服务在 `runs/` 保存实际 JEV 请求／响应（`*-jev.jsonl`）和应用动作／结算（`*-moves.jsonl`）。不记录 API Key，不通过网页静态路由公开这些文件。网页牌局本身只在内存中，重启会清空；所有窗口共享同一牌桌，不是多人联网服务。

## 权重来源与规则边界

- 上游：[kwai/DouZero](https://github.com/kwai/DouZero)，Apache-2.0，使用 `douzero==1.1.0` 的模型结构及特征编码。
- 下载的是 [PerfectDou 官方仓库随评测发布的 DouZero ADP 基线](https://github.com/Netease-Games-AI-Lab-Guangzhou/PerfectDou/tree/594404922ee3810e2d84b80bb2c2846cb20e5390/perfectdou/model/douzero/douzero_ADP)，**不是 PerfectDou 模型**。固定提交及三个 SHA-256 见 `models/manifest.json`。权重不提交仓库，不重新训练。
- 地主、地主下家、地主上家使用各自预训练权重；只使用当前玩家的可见信息，不读取其他人真实手牌。未知合并牌池由全牌堆减自己手牌与公开已出牌计算。
- 标准 DouZero 模型只有出牌策略。**DouZero 座位的叫分采用固定 `FullSimpleAgent` 策略**，JEV 座位自行决定叫分，不宣称 DouZero 支持叫地主。
- 规则仍由本仓库完整引擎负责（叫分、春天、炸弹及全部经典牌型）；模型对本引擎给出的合法动作评分，不能输出非法动作。部分翅膀细则及计分与预训练环境可能不同，不把该适配宣称为原论文成绩复现。
- 牌面花色为装饰，规则引擎记录点数。

## 本地接口

- `GET /api/state`：仅 p0 可见手牌、公开状态、合法动作、历史、版本号、控制方式及错误状态，不暴露对手手牌或未公开底牌。
- `POST /api/command`，JSON：
  - `{"command":"configure","controller":"jev","jev_mode":"minimal"}`：配置并开始新局；控制方式 `human/douzero/jev`，信息模式 `minimal/assisted`。
  - `{"command":"mode","auto":true}`：按当前配置开启连续对局。
  - `{"command":"speed","delay":0.9}`：每步间隔 0.1–5 秒，不含实际推理耗时。
  - `{"command":"new"}`：重新发牌。
  - `{"command":"retry"}`：清除错误并按当前控制方式恢复。
  - `{"command":"hint","revision":3}`：手动模式获取本地对手模型建议，不产生 JEV 调用。
  - `{"command":"action","revision":3,"action_id":"bid:1"}`：手动操作 p0；需最新版本号及合法动作 ID。

仍保留无依赖演示：`python3 games/doudizhu/server.py --opponent simple`，此时页面会标明「简单 AI」，不是 DouZero。

## 验证

```sh
python3 -m unittest discover -s tests
python3 -m unittest discover -s games/doudizhu -p 'test_*.py'
```

默认测试不下载模型、不请求 JEV API。首次部署后可使用 DouZero 自对局验证已下载权重，再显式运行配对对照。
