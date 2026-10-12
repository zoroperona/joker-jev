# JEV / TypeSafe 接入

依据官方 [Introduction](https://docs.typesafe.ai/introduction)、[Quick start](https://docs.typesafe.ai/introduction/quickstart) 和 [API reference](https://docs.typesafe.ai/api)。Jev 是 System One 模型，输入 `state` 和类型化 `questions`，输出结构化判断；支持 Choice、Score 和 Noul。本项目目前使用 Choice 选择合法动作。

## 配置与运行

本地 `.env`（不提交），格式参考仓库 `.env.example`：

```dotenv
TYPESAFE_API_URL=https://api.typesafe.ai/v1/systemone
TYPESAFE_API_KEY=your-key
TYPESAFE_MODEL=jev-latest
```

```bash
python3 -m joker_jev --agent jev --seed 42
```

默认首位玩家使用 Jev，对手使用随机基线。配置也可通过环境变量传入，优先于 `.env`；可用 `--env-file` 指定其他文件。文件支持空行、整行注释及可选引号的 `KEY=VALUE`，不执行变量展开、shell 或行尾注释。

当前用 Python 标准库直接调用 HTTP API，兼容 Python 3.9；官方 Python SDK 要求 Python 3.10+。

```python
from joker_jev.agents.jev import JEVAgent
from joker_jev.agents.typesafe import TypeSafeBackend
from joker_jev.agents.base import RandomAgent
from joker_jev.core.engine import play
from joker_jev.games import create_game

backend = TypeSafeBackend.from_env()
result = play(create_game("high_card"), {
    "p0": JEVAgent(backend), "p1": RandomAgent(7),
}, seed=42)
print(result.rewards)
```

## 请求与响应

请求为 `POST /v1/systemone`，使用 `Authorization: Bearer <key>`。密钥仅用于请求头，不放入模型状态、对局日志或错误信息。

```json
{
  "model": "jev-latest",
  "state": {"rules": "实际为规则对象", "observation": "实际为玩家观察对象", "belief": "实际为推断对象"},
  "questions": {
    "next_action": {
      "type": "choice",
      "instructions": "Which legal action best serves the current player's reward objective in rules?",
      "criteria": {
        "play:3": {"label": "出 3", "payload": {"card": 3}},
        "play:5": {"label": "出 5", "payload": {"card": 5}}
      }
    }
  }
}
```

上例仅展示结构，实际 `state` 是完整的 `DecisionContext`，包含协议版本、规则与奖励、当前玩家可见的公共/私有信息、合法动作、公开历史、推断事实/估计/假设、自身累计奖励，不含对手底牌或洗牌种子。

读取响应中的 `answers.next_action.choice` 作为动作 ID，同时校验 `type`、`probabilities` 和 `confidence`。最近一次成功的原始响应保存在 `backend.last_response`，可查看模型版本、概率、置信度和 usage。`Choice` 概率是选项的模型分布，**不是该动作的获胜概率或期望收益**；Jev 不生成文字理由。

底层 `JEVAgent` 仍支持注入 `backend(request_json: str) -> str`，便于离线测试。这里的内部 JSON 协议由 `TypeSafeBackend` 转换为官方 API 格式，再把答案转换为 `{"action_id": "..."}`；不能把内部请求直接发送到官方端点。

## 当前范围

- 每个决策使用一个 Choice 问题；这是基本策略接入，不是博弈搜索或训练。官方建议将复杂判断拆为原子问题，后续可加入动作价值分项评分及代码聚合。
- Choice 最多 255 个候选项；通用适配器超出明确报错，不能静默截断。完整斗地主的 `FullJEVAgent` 已实现牌型、主体、具体出法的分层选择，见 [完整斗地主](full-doudizhu.md)。
- 唯一合法动作由代码直接选择，不调用 API，此时 `last_response` 为 `None`。
- 请求超时默认为 30 秒；HTTP、网络和非法响应直接报错，不静默换成随机策略，不自动重试消耗额度。429/529 如需重试，应使用有上限的指数退避。
- 终局后不再请求 Agent，结果由 `play` 返回；训练与经验回放需独立接口。

斗地主残局模块另外使用 `TypeSafeBackend.evaluate(state, questions)`：先批量发出四个原子 Noul 战术问题，再以 Choice 选牌。调用方分别校验答案类型、概率范围和合法动作。详见 [斗地主策略实验](../joker_jev/games/doudizhu/README.md)，它不改变已有比牌示例的单阶段接入。
