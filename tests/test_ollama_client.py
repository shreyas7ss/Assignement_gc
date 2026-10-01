import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.ollama_client import OllamaRestClient


class OllamaClientTests(unittest.TestCase):
    def test_chat_request_uses_local_image_and_json_schema(self) -> None:
        response_data = {
            "message": {"content": json.dumps({"ok": True})},
            "prompt_eval_count": 80,
            "eval_count": 20,
            "total_duration": 1_250_000_000,
        }
        response = unittest.mock.Mock()
        response.__enter__ = unittest.mock.Mock(return_value=response)
        response.__exit__ = unittest.mock.Mock(return_value=False)
        response.read.return_value = json.dumps(response_data).encode("utf-8")
        client = OllamaRestClient(base_url="http://127.0.0.1:11434")

        with patch("app.ollama_client.urlopen", return_value=response) as urlopen:
            text = client.generate_content(
                model="qwen3-vl:8b",
                system_instruction="Return JSON",
                prompt="Read this page",
                parts=[
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,abc"},
                    }
                ],
                response_schema={
                    "type": "object",
                    "properties": {"ok": {"type": "boolean"}},
                    "required": ["ok"],
                },
            )

        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/chat")
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["model"], "qwen3-vl:8b")
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["format"]["required"], ["ok"])
        self.assertEqual(payload["messages"][1]["images"], ["abc"])
        self.assertEqual(text, '{"ok": true}')
        self.assertEqual(client.last_usage["tokens_in"], 80)
        self.assertEqual(client.last_usage["tokens_out"], 20)
        self.assertEqual(client.last_usage["latency_ms"], 1250.0)

    def test_image_data_url_is_required_for_image_part(self) -> None:
        client = OllamaRestClient(base_url="http://127.0.0.1:11434")

        with patch("app.ollama_client.urlopen"):
            with self.assertRaisesRegex(ValueError, "base64 data URL"):
                client.generate_content(
                    model="qwen3-vl:8b",
                    system_instruction="Return JSON",
                    prompt="Read image",
                    parts=[{"type": "image_url", "image_url": {"url": "https://example.test/image.png"}}],
                    response_schema={"type": "object"},
                )


if __name__ == "__main__":
    unittest.main()