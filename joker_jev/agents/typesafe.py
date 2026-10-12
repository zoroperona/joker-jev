"""TypeSafe System One HTTP 后端，将合法动作映射为 Choice。"""

import json
import math
import os
from pathlib import Path
from typing import Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

DEFAULT_ENDPOINT = "https://api.typesafe.ai/v1/systemone"


class TypeSafeError(RuntimeError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_env(path: str) -> Dict[str, str]:
    """读取简单 KEY=VALUE 文件，不执行 shell，不修改进程环境。"""
    file = Path(path)
    if not file.exists():
        return {}
    values = {}
    for line_number, line in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not key.strip().isidentifier():
            raise ValueError(".env 第 %d 行需要 KEY=VALUE 格式" % line_number)
        value = value.strip()
        if value.startswith(("'", '"')):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError(".env 第 %d 行引号未闭合" % line_number)
            value = value[1:-1]
        values[key.strip()] = value
    return values


class TypeSafeBackend:
    def __init__(self, api_key: str, endpoint: str = DEFAULT_ENDPOINT,
                 model: str = "jev-latest", timeout: float = 30.0):
        if not api_key.strip():
            raise ValueError("请在 .env 或环境变量中设置 TYPESAFE_API_KEY")
        url = urlsplit(endpoint)
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            raise ValueError("TYPESAFE_API_URL 必须是无内嵌凭据的 HTTPS 地址")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout 必须为有限正数")
        self._api_key = api_key.strip()
        self.endpoint = endpoint
        self.model = model
        self.timeout = timeout
        self.last_response: Optional[dict] = None
        self._opener = build_opener(_NoRedirect())

    @classmethod
    def from_env(cls, env_file: str = ".env"):
        config = read_env(env_file)
        config.update(os.environ)
        return cls(
            api_key=config.get("TYPESAFE_API_KEY", ""),
            endpoint=config.get("TYPESAFE_API_URL", DEFAULT_ENDPOINT),
            model=config.get("TYPESAFE_MODEL", "jev-latest"),
        )

    def __call__(self, request_json: str) -> str:
        self.last_response = None
        context = json.loads(request_json)["context"]
        actions = context["observation"]["legal_actions"]
        criteria = {a["id"]: {"label": a["label"], "payload": a["payload"]} for a in actions}
        if not criteria or len(criteria) != len(actions):
            raise ValueError("Choice 需要非空且 ID 唯一的合法动作")
        if len(criteria) > 255:
            raise ValueError("TypeSafe Choice 最多支持 255 个动作；该游戏需要分层选择策略")
        if len(criteria) == 1:
            return json.dumps({"action_id": next(iter(criteria)), "reason": "唯一合法动作，由代码直接选择"})
        data = self.evaluate(context, {
            "next_action": {
                "type": "choice",
                "instructions": (
                    "Which legal action best serves the current player's reward objective in rules? "
                    "Use the visible observation, reward rules and belief assumptions. "
                    "Belief estimates are uncertain, not actual opponent cards."
                ),
                "criteria": criteria,
            },
        })
        # 只有完整校验后才发布成功响应。
        self.last_response = None
        try:
            answer = data["answers"]["next_action"]
            choice = answer["choice"]
            probabilities = answer["probabilities"]
            confidence = answer["confidence"]
            if answer["type"] != "choice" or choice not in criteria:
                raise ValueError()
            if not isinstance(probabilities, dict) or set(probabilities) != set(criteria):
                raise ValueError()
            for number in [confidence, *probabilities.values()]:
                if isinstance(number, bool) or not isinstance(number, (int, float)) or not 0 <= number <= 1:
                    raise ValueError()
            if not math.isclose(sum(probabilities.values()), 1.0, abs_tol=0.01):
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise TypeSafeError("TypeSafe 返回了无效的 Choice 答案") from None
        self.last_response = data
        return json.dumps({"action_id": choice})

    def evaluate(self, state: dict, questions: dict) -> dict:
        """发送独立的类型化问题；各调用方继续校验其答案类型和范围。"""
        self.last_response = None
        if not questions:
            raise ValueError("questions 不能为空")
        payload = {"model": self.model, "state": state, "questions": questions}
        request = Request(self.endpoint,
                          data=json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8"),
                          headers={"Authorization": "Bearer " + self._api_key,
                                   "Content-Type": "application/json", "Accept": "application/json"},
                          method="POST")
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                data = json.load(response)
        except HTTPError as exc:
            status = exc.code
            exc.close()
            raise TypeSafeError("TypeSafe 请求失败，HTTP %d" % status) from None
        except (URLError, OSError):
            raise TypeSafeError("TypeSafe 网络请求失败或超时") from None
        except (ValueError, UnicodeError):
            raise TypeSafeError("TypeSafe 响应不是有效 JSON") from None
        if not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
            raise TypeSafeError("TypeSafe 响应缺少 answers")
        if set(data["answers"]) != set(questions):
            raise TypeSafeError("TypeSafe 回答的问题与请求不一致")
        self.last_response = data
        return data
