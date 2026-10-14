# 截图驱动的外部斗地主工具

开发入口：`python -m joker_jev.external`。这是独立进程，接入现有 `games/doudizhu` 网页牌桌；原有引擎、自对弈和 JEV 策略实验保留用于对照。

```text
浏览器截图 PNG
  → ScreenReader（布局/记录 OCR；手牌可选 Jev 图片识别或本地字形匹配）
  → PublicState（公开事件、左右剩余牌数、自己手牌、轮次）
  → DouZeroPolicy（三个身份的冻结 ADP 权重）
  → UIMapper（Jev 接收截图，将指定牌映射到画面中的牌和按钮）
  → Playwright 鼠标坐标点击
  → 下一张截图确认自己的实际出牌
```

运行中的外部客户端不导入牌桌 server、不读取 DOM/JS、网络响应、`/api/state`、`/api/command`、引擎状态或服务器合法动作。浏览器页面自身的正常请求不受影响。客户端用规则模块在本地生成合法动作；对手未知手牌只保留为合并未知牌池，不猜成真实分配。

## Jev 图片协议

参考用户指定的 `jevlink-replay/Tools/jevlink` 中 `electron/tcp/game-api.js`、`electron/jev/client.js` 和 `electron/jev/loop.js` 实现：System One 请求在 `model/state/questions` 同级携带 `images`。接受 PNG/JPEG/WebP 的 Base64 Data URL，或严格的 `{mediaType, base64}` 对象，保留顺序；最多 4 张、解码后单张 4 MiB、合计 8 MiB，带图请求完整 JSON 最多 13 MiB。编码、大小或端点错误均停止，不删图重试。

`--vision jev` 将每张手牌的角标从截图裁出，每张牌独立请求，要求 Jev 从像素选择点数。请求不包含本地识别的点数答案；未知、低置信度、顺序或牌数校验失败都停止。当前布局定位、玩家计数、身份和可见出牌记录仍由 macOS OCR 读取；尚未将整桌所有字段改成 Jev 识别。

`--ui-policy jev`（默认）将当前截图分别用于回合文字、按钮标签和每张目标牌的独立识别。牌面请求不提供期望点数，由客户端将识别结果与 DouZero 指定动作比较；每项模型置信度至少 0.8。对于不选牌的按钮操作，当前绿色牌桌专用的像素适配器额外区分亮色文字/金色填充与禁用的暗色样式；未知样式停止。该适配器只读取截图，不读取 DOM 或游戏状态，换皮肤需要重新验证。出牌按钮在选牌前可能禁用，当前不在此阶段要求它启用。点击前仍检查画面是否变化，点击后通过下一张截图的可见历史确认结果。Jev 不选择斗地主打法；鼠标由执行器调用。

`--ui-policy jev-text` 显式使用原来的文本映射；`--ui-policy local` 显式使用确定性坐标映射。这两个模式都不会向 UI 映射请求附图，不是图片失败时的回退。`--vision local` 为默认的本地牌面识别，和 UI 模式分别配置。

**端点验证状态：** 当前 `.env` 中的 `jev-latest` 对文本请求成功，对带顶层 `images` 的请求返回 HTTP 400（`api_usage_error: Invalid request.`）。进一步固定为 JevLink 默认的 `jev-1.13.0` 测试：Data URL 和 `{mediaType, base64}` 两种图片表示均返回 HTTP 400；同一模型的文本对照请求成功，响应确认模型为 `jev-1.13.0`。见 [固定版本探测记录](../reports/jev-1.13-image-probe.json)。这仅是官方端点的探测结果。另一个自建兼容服务已接受图片并返回 `pplx-decider-v1.1-27b`，原多牌请求出现错误，当前单牌请求已通过 37 张开发样本对照，图片整局验证进展见研究记录。JevLink 的客户端支持转发图片，不足以证明任意端点/模型都支持。公开部署与配置方式见 [可复现视觉后端](vision-backends.md)，不依赖开发者的内网机器。此前“Jev 不支持图片”的笼统结论由本节更正。

## 运行

首版视觉配置针对 **macOS + 现有网页 + 1440×1600 浏览器视口 + 2 倍像素密度 + 100% 缩放**。工具创建自己的浏览器窗口并设置尺寸；不要求手工调整系统显示器。需要 Xcode Command Line Tools 的 `swiftc`、系统 Vision 框架和 Georgia 字体。其他操作系统/游戏布局需更换 `ScreenReader`。

```sh
# 准备已有权重环境
bash games/doudizhu/setup.sh
uv pip install --python games/doudizhu/.venv/bin/python -e '.[external]'
games/doudizhu/.venv/bin/python -m playwright install chromium

# 终端一：牌桌保持手动模式。对手仍由游戏自身控制。
bash games/doudizhu/start.sh --port 8877 --seed 42 --delay 1.5

# 终端二：图片模式；先在 .env 配置已验证支持 images 的端点和模型。
games/doudizhu/.venv/bin/python -m joker_jev.external \
  --url http://127.0.0.1:8877 --execute --bid 3 --vision jev --ui-policy jev \
  --output games/doudizhu/runs/external-001
```

`--output` 必须是尚不存在的目录；逐帧 PNG、识别结果、结构化出牌和模型决策保存在其中。默认 300 秒超时，一局结束后退出。工具不会自动重新开局。重跑时先在网页点“重新发牌”，使用新的输出目录。

不传 `--execute` 时只观察并输出首次出牌建议，不点击。此时在其他牌桌窗口完成叫分即可。`--bid 0..3` 是用户显式指定的固定叫分，不是模型叫分；不传该参数则等待用户叫分。DouZero ADP 只有出牌权重。

使用当前文本端点运行原闭环：`--vision local --ui-policy jev-text`。无需 Jev 的集成诊断：`--vision local --ui-policy local`。后台验证可增加 `--headless`。不要开启牌桌的自动托管，它会与外部玩家争夺自己的座位。

## 识别与状态

左右玩家的手牌数量和身份来自桌面文字；自己的手牌来自牌面像素。现有页面没有分别保留两家的完整出牌区域，因此首版还通过 OCR 读取**屏幕可见的“牌桌手记”**，获得每手牌的点数与过牌，以及可见行号；没有读取该记录的底层数据。新布局可替换为左右出牌区检测，复用其余管线。

确认事件为 `{sequence, seat, cards, remaining}`，其中 `seat` 为 `self/right/left`，`count=len(cards)`，空牌表示过牌。实际出牌顺序是自己 → 右边 → 左边；地主身份映射为 DouZero 的地主、地主下家、地主上家。不能只用两家最近一手：模型还需要自己手牌、完整出牌/过牌序列、各家累计已出牌、当前牌权、剩余张数、炸弹数。

状态层校验事件顺序、重复事件、牌堆重数、剩余数量、牌型和压制关系，两家连续过牌后归还牌权。只有截图确认自己的出牌才扣除手牌，提交鼠标点击本身不算成功。推理期间牌桌画面变化会取消执行；提交后未确认会停止，不盲目重发。

## 当前限制

- 从叫分结束/首手出牌之前开始跟踪；不支持中途接管、缺失历史恢复和自动切局。
- 固定布局和字体；屏幕部分被裁掉的记录不参与识别。漏行、低质量识别、规则解释歧义、牌数不一致都会停止。
- 屏幕只能显示最近数手；过快的对手节奏可能超出采集速度。首版使用 1.5 秒节奏验证。
- 规则沿用本仓库经典斗地主，翅膀等规则与预训练环境存在差异；不支持癞子或其他变体。
- 本地画面验证不等于任意界面识别能力或胜率评测。

## 验证记录

2026-10-14：原文本 Jev UI 映射完整对局通过（对应现在的 `--ui-policy jev-text`，未发送图片），种子 43、固定叫 3 分、对手间隔 1.5 秒；14 次出牌决策和对应 Jev UI 映射，42 手截图确认的出牌/过牌。覆盖重复点数、顺子、连对、王炸和连续过牌。该局外部玩家为地主，农民获胜；这是闭环验证，不是胜率结论。

[结构化验证记录](../reports/external-player-jev-smoke.json)。逐帧原始截图与完整响应只保留在本机；之前的识别/映射失败也未计为成功。

```sh
# 核心、截图回归与原有测试（截图测试需 macOS + Pillow + Swift）
games/doudizhu/.venv/bin/python -m unittest discover -s tests
# 原有网页服务器测试
games/doudizhu/.venv/bin/python -m unittest discover -s games/doudizhu -p 'test_*.py'
```

农民视角补充验证：种子 44、固定不叫、显式 `--ui-policy local`，完整确认 25 手出牌/过牌。该项不调用 Jev，用于验证地主身份映射和农民输入。见 [结构化记录](../reports/external-player-farmer-smoke.json)，原始截图只保留在本机。

图片输入方式的对照、消融实验与 UI 核对修正见 [图片识别输入研究](vision-research.md)。
