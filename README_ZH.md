# Joker + JEV

[English](README.md) | 中文

通过截图操作游戏的独立斗地主工具。**DouZero 开源预训练权重决定出牌，Jev 兼容视觉服务识别 UI 目标，执行器点击后用下一张截图确认结果。** 外部玩家不读取游戏 API、DOM、JavaScript 状态或对手隐藏手牌。

`main` 以这条架构为主线。原先由 JEV 决定策略的完整版本已保留在 [`old-feat/jev-decision`](https://github.com/zoroperona/joker-jev/tree/old-feat/jev-decision)，包含原文档与实验结果。当前代码树保留共享规则和旧评测工具，供兼容与对照使用。

## 当前流程

```text
截图 → 自己手牌与可见公开事件 → 公共状态
     → DouZero 决策 → 视觉核对 UI → 鼠标点击
     → 下一张截图确认实际出牌
```

手牌点数可由支持图片的 System One 服务识别；布局、玩家牌数、身份和可见牌桌记录目前由 macOS OCR 读取。按钮样式使用当前绿色牌桌专用的像素适配器。Jev 负责识别与 UI 映射，不选择斗地主打法；叫分由用户手动完成或通过 `--bid` 明确指定。

## 快速开始

当前截图配置需要 **macOS、Python 3.11、uv、Xcode Command Line Tools（`swiftc`）及支持图片的视觉服务**。适配的是仓库内网页牌桌，视口 1440×1600、2 倍像素密度，尚未通用适配其他游戏和皮肤。

```sh
git clone https://github.com/zoroperona/joker-jev.git
cd joker-jev
bash games/doudizhu/setup.sh
uv pip install --python games/doudizhu/.venv/bin/python -e '.[external]'
games/doudizhu/.venv/bin/python -m playwright install chromium
cp configs/vision-local.env.example .env.vision
```

编辑 `.env.vision`，接入自己的服务。示例指向 localhost，不会自动启动模型服务器。模型、硬件与协议要求见 [视觉后端与自建部署](docs/vision-backends.md)。兼容 Jev 协议或模型别名不等于支持图片；此前测试的官方端点拒绝图片请求。公开配置不依赖开发者内网服务，也不包含密钥。

```sh
# 终端一：自己的座位保持手动模式，对手由 DouZero 控制
bash games/doudizhu/start.sh --port 8877 --seed 42 --delay 1.5

# 终端二：仅通过截图操作，显式固定叫 3 分
games/doudizhu/.venv/bin/python -m joker_jev.external \
  --url http://127.0.0.1:8877 --env-file .env.vision \
  --execute --bid 3 --vision jev --ui-policy jev \
  --output games/doudizhu/runs/external-001
```

每次运行使用新的输出目录，牌桌不要开启自动托管。工具创建自己的浏览器窗口，完成一局后退出；不支持中途接管。画面变化、目标无法识别或点击结果未确认时停止，不盲目重试。

## 验证与限制

- 当前开发环境中，119 项主测试和 7 项网页服务器测试通过。
- 图片流程种子 46 完整确认 37 手出牌/过牌；未参与调试的种子 47 完整确认 21 手。这是闭环完成验证，不是胜率或长期可靠性结论。
- 当前通过屏幕可见的“牌桌手记”重建左右玩家事件；分别识别左右出牌区域仍需新增界面适配。
- 布局、字体、颜色与可见记录行数限制兼容范围；已验证对手节奏为 1.5 秒。外部策略始终不接收对手隐藏手牌。

```sh
games/doudizhu/.venv/bin/python -m unittest discover -s tests
games/doudizhu/.venv/bin/python -m unittest discover -s games/doudizhu -p 'test_*.py'
```

[架构与执行细节](docs/external-player.md) · [视觉后端配置](docs/vision-backends.md) · [研究与失败记录](docs/vision-research.md) · [网页牌桌](games/doudizhu/README.md) · [玩法规则](docs/full-doudizhu.md)

私有 `.env`、下载的模型权重和运行截图/日志均被 Git 忽略。公开报告与测试截图来自合成牌局。
