from dataclasses import asdict
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from joker_jev.agents.typesafe import TypeSafeBackend, TypeSafeError, read_env
from joker_jev.agents.jev import JEVAgent
from joker_jev.core.models import DecisionContext, Observation
from joker_jev.games.high_card.game import HighCardGame


class TypeSafeTests(unittest.TestCase):
    def setUp(self):
        game = HighCardGame()
        state = game.initial_state(42)
        view = game.view(state, "p0")
        obs = Observation("high_card", "p0", 0, view.private, view.public,
                          game.legal_actions(state), ())
        self.context = DecisionContext(game.rules, obs, game.create_inference().infer(obs), 0)
        self.ids = [a.id for a in obs.legal_actions]
        self.backend = TypeSafeBackend("test-key")
        self.backend._opener = Mock()

    def response(self):
        return {"model": "jev-test", "answers": {"next_action": {
            "type": "choice", "choice": self.ids[0], "confidence": 0.6,
            "probabilities": dict(zip(self.ids, [0.8, 0.1, 0.1])),
        }}, "usage": {"input_tokens": 100, "output_tokens": 20}}

    def set_response(self, data):
        self.backend._opener.open.return_value = io.BytesIO(json.dumps(data).encode())

    def test_official_request_and_response_mapping(self):
        self.set_response(self.response())
        result = JEVAgent(self.backend).decide(self.context)
        request = self.backend._opener.open.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        self.assertEqual(payload["model"], "jev-latest")
        self.assertEqual(payload["state"]["observation"]["private"], self.context.observation.private)
        self.assertEqual(set(payload["questions"]["next_action"]["criteria"]), set(self.ids))
        self.assertNotIn("test-key", request.data.decode())
        self.assertEqual(result.action_id, self.ids[0])
        self.assertEqual(result.reason, "")
        self.assertEqual(self.backend.last_response, self.response())

    def test_malformed_answers_rejected(self):
        for change in ({"choice": "illegal"}, {"confidence": float("nan")},
                       {"probabilities": {}}, {"confidence": True}, {"type": "noul"}):
            with self.subTest(change=change):
                data = self.response()
                data["answers"]["next_action"].update(change)
                self.set_response(data)
                with self.assertRaises(TypeSafeError):
                    JEVAgent(self.backend).decide(self.context)
                self.assertIsNone(self.backend.last_response)

    def test_errors_do_not_expose_response_or_key(self):
        for error in (HTTPError(self.backend.endpoint, 401, "test-key", {}, io.BytesIO(b"test-key")),
                      URLError("test-key"), TimeoutError("test-key")):
            self.backend._opener.open.side_effect = error
            with self.assertRaises(TypeSafeError) as caught:
                JEVAgent(self.backend).decide(self.context)
            self.assertNotIn("test-key", str(caught.exception))

    def test_forced_action_skips_network_and_large_choice_fails(self):
        context = asdict(self.context)
        context["observation"]["legal_actions"] = [context["observation"]["legal_actions"][0]]
        result = json.loads(self.backend(json.dumps({"context": context})))
        self.assertEqual(result["action_id"], self.ids[0])
        self.backend._opener.open.assert_not_called()
        context["observation"]["legal_actions"] = [
            {"id": str(i), "label": str(i), "payload": {}} for i in range(256)]
        with self.assertRaisesRegex(ValueError, "255"):
            self.backend(json.dumps({"context": context}))
        self.backend._opener.open.assert_not_called()

    def test_environment_precedence_and_missing_key(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text('# comment\nTYPESAFE_API_KEY="file-key"\nTYPESAFE_MODEL=jev-pinned\n')
            self.assertEqual(read_env(str(path))["TYPESAFE_API_KEY"], "file-key")
            with patch.dict(os.environ, {"TYPESAFE_API_KEY": "env-key"}, clear=True):
                backend = TypeSafeBackend.from_env(str(path))
                self.assertEqual(backend._api_key, "env-key")
                self.assertEqual(backend.model, "jev-pinned")
            with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(ValueError, "TYPESAFE_API_KEY"):
                TypeSafeBackend.from_env(str(path.parent / "missing"))


if __name__ == "__main__":
    unittest.main()
