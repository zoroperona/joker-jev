# 可复现的视觉后端

外部斗地主客户端依赖 System One 图片协议，不绑定开发者的内网服务器。斗地主打法来自 DouZero；视觉/操作映射可以使用兼容的决策模型。请求模型名、响应模型名应分别记录，不能将兼容别名当成实际模型。

## 本地测试与公开发布

- 本地开发使用已配置的内网视觉服务，通过 `--env-file .env.vision` 选择；该文件只保存在本机。
- GitHub 仅提供 `configs/*.env.example` 通用模板、公开模型来源和部署说明，不将开发者内网服务作为默认依赖。
- 本地截图、完整响应和运行日志保存在被忽略的 `games/doudizhu/runs/`；发布测试报告时另行整理，不直接提交原始会话目录。
- 公开报告分别标明请求模型、实际返回模型、视觉模式和验证范围，区分内网实测、文本模式整局测试及尚未实测的自部署方案。
- 提交或推送前检查待发布差异及新增文件，排除内网地址、凭证、本机配置、权重与原始会话日志。

## 模型选择

| 方案 | 公开来源 | 环境要求（上游说明） | 本项目验证状态 |
| --- | --- | --- | --- |
| Perplexity 官方 BF16 | [perplexity-ai/pplx-decider-v1.1-27b](https://huggingface.co/perplexity-ai/pplx-decider-v1.1-27b) | Python 3.12+、CUDA、约 49 GiB 权重显存，另需运行空间 | 已调用返回该模型名的现有服务；没有从头部署验证 |
| 社区 MLX 4-bit | [mlx-community/pplx-decider-v1.1-27b-4bit](https://huggingface.co/mlx-community/pplx-decider-v1.1-27b-4bit) | Apple Silicon、Python 3.12+、至少 24 GB 内存；上游称运行约 16 GB | 尚未部署、未验证精度及图片接口 |
| 自选托管服务 | 用户自己的 System One 图片端点 | 服务商规定 | 不能因为兼容文本协议就推断支持图片 |
| 本地识别 | 本项目 `--vision local --ui-policy local` | macOS Vision、Swift、Pillow、已有 DouZero 环境 | 已跑通当前网页整局；不需要视觉模型服务器 |

Perplexity 模型为 Apache-2.0 开源权重，基于 Qwen3.8-27B，属于多模态分类/决策模型。返回候选概率，不生成任意聊天文本，也不是斗地主专用模型。它使用独立的 255 类 readout、非因果完整注意力和校准温度；不能直接用普通聊天模型加载方式替代上游实现。Decision Index 成绩不是本项目牌面识别率。

官方模型卡“Usage”仍有 private repository 的文字，但查询时仓库 API 标记 `private=false`、`gated=false`，README/服务源码可匿名读取；实际下载权限以 Hugging Face 当时状态为准。

## 官方 CUDA 服务

以下命令依据固定公开版本源码编写，未在本机完成 GPU 部署。不要与斗地主 Python 3.11 环境混用：推理服务器使用独立 Python 3.12 环境，并需要下载约 52 GB 权重。

```sh
uv venv .venv-decider --python 3.12
uv pip install --python .venv-decider/bin/python huggingface-hub
.venv-decider/bin/hf download perplexity-ai/pplx-decider-v1.1-27b \
  --revision 14c9d90137962d300f3de95633f7b6535e80c5ce \
  --local-dir .models/pplx-decider
uv pip install --python .venv-decider/bin/python -r .models/pplx-decider/requirements.txt
AUTOJEV_CHECKPOINT="$PWD/.models/pplx-decider" \
PYTHONPATH="$PWD/.models/pplx-decider/source/src" \
  .venv-decider/bin/python -m autojev.server
```

默认监听 `127.0.0.1:8000`，检查 `GET /health`，推理入口为 `POST /v1/systemone`。上游支持 `AUTOJEV_API_KEY` 启用 Bearer 认证；未设置时无需 Key。若部署在独立 GPU 机器，客户端填自己的可达地址及对应认证配置。

[官方 server.py](https://huggingface.co/perplexity-ai/pplx-decider-v1.1-27b/blob/14c9d90137962d300f3de95633f7b6535e80c5ce/source/src/autojev/server.py) 接受 `jev-1.13.0` 等兼容别名，实际执行的是加载的 Perplexity 权重；`/health` 和响应 `model` 以服务实际返回值为准。官方该版本的 HTTP `images` 接受 Data URL 字符串，本客户端的图片调用使用该形式。

## Apple Silicon 社区服务

下面是公开社区项目的复现入口，未验证它与官方 BF16 的逐项等价性。不要用普通 `mlx_lm.load` / `mlx_vlm.load` 代替它附带的实现。

```sh
uv venv .venv-decider-mlx --python 3.12
uv pip install --python .venv-decider-mlx/bin/python huggingface-hub
.venv-decider-mlx/bin/hf download mlx-community/pplx-decider-v1.1-27b-4bit \
  --revision 66383f28b37637658b02b8e82b1029598b138642 \
  --local-dir .models/pplx-decider-mlx
uv pip install --python .venv-decider-mlx/bin/python -r .models/pplx-decider-mlx/requirements.txt
.venv-decider-mlx/bin/python .models/pplx-decider-mlx/server.py \
  --model .models/pplx-decider-mlx --port 8000
```

## 斗地主客户端配置

```sh
cp configs/vision-local.env.example .env.vision
# 编辑 .env.vision：填写自己的服务地址、模型及认证方式。
games/doudizhu/.venv/bin/python -m joker_jev.external \
  --env-file .env.vision --url http://127.0.0.1:8877 \
  --vision jev --ui-policy jev --execute --bid 3 \
  --output games/doudizhu/runs/vision-001
```

`--vision jev` / `--ui-policy jev` 是协议模式名，不保证实际后端为 TypeSafe Jev。`TYPESAFE_AUTH=none` 明确不发送 Authorization，即使其他配置来源存在 Key；`TYPESAFE_ALLOW_HTTP=1` 显式启用本地/自建 HTTP。保留原 `.env` 的官方服务配置，使用独立 `.env.vision`；shell 同名环境变量仍优先于文件。`.env.vision` 不进入 Git。

`configs/vision-remote.env.example` 是自选 HTTPS 服务的模板，不声明任何公共商业服务已通过图片兼容性验证。当前查询 OpenRouter 通用模型列表未找到该 Decider 条目，因此暂不提供未经核实的托管模型 ID。

## 能力边界与验收

现有兼容服务已接受图片。原多图请求在 37 张开发样本中答对 33 张；单牌请求答对 37 张，已切换为单牌方式。完整对照和整局验证状态见 [图片识别输入研究](vision-research.md)。这不是通用识别准确率保证。高置信度也可能答错。默认停止错误执行，不自动回退为文本模式。

图片模式需要逐项验证：单牌、同点数多牌、大小王、多图顺序、整手牌一致性、按钮定位和完整对局。当前仍使用固定网页布局与本地 OCR 读取玩家身份、剩余张数和可见历史；通用跨游戏视觉适配尚未完成。

在没有兼容视觉后端时，可以运行已验证的本地路径：

```sh
games/doudizhu/.venv/bin/python -m joker_jev.external \
  --vision local --ui-policy local --execute --bid 3 \
  --output games/doudizhu/runs/local-001
```
