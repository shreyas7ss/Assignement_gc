from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OllamaAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class OllamaRestClient:
    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:11434",
        timeout: int = 180,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.last_usage: dict[str, int | float | None] = {}

    def generate_content(
        self,
        *,
        model: str,
        system_instruction: str,
        prompt: str,
        parts: list[dict[str, Any]],
        response_schema: dict[str, Any],
    ) -> str:
        request_started = time.perf_counter()
        self.last_usage = {}
        message: dict[str, Any] = {
            "role": "user",
            "content": prompt,
        }
        images = _extract_images(parts)
        if images:
            message["images"] = images

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_instruction},
                message,
            ],
            "stream": False,
            "format": response_schema,
            "options": {"temperature": 0, "num_predict": 3000},
        }
        request = Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                response_data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            message = _error_message(exc.read())
            suffix = f": {message}" if message else ""
            raise OllamaAPIError(
                f"Ollama returned HTTP {exc.code}{suffix}",
                status_code=exc.code,
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise OllamaAPIError(
                f"Cannot reach Ollama at {self.base_url}; ensure Ollama is running"
            ) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OllamaAPIError("Ollama returned an unreadable response") from exc

        try:
            text = response_data["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise OllamaAPIError("Ollama returned no chat content") from exc
        if not isinstance(text, str) or not text.strip():
            raise OllamaAPIError("Ollama returned empty chat content")

        self.last_usage = {
            "latency_ms": response_data.get(
                "total_duration",
                (time.perf_counter() - request_started) * 1_000_000,
            )
            / 1_000_000,
            "tokens_in": response_data.get("prompt_eval_count"),
            "tokens_out": response_data.get("eval_count"),
        }
        return text


def _extract_images(parts: list[dict[str, Any]]) -> list[str]:
    images: list[str] = []
    for part in parts:
        if part.get("type") != "image_url":
            continue
        image_url = part.get("image_url", {}).get("url", "")
        if not isinstance(image_url, str) or not image_url.startswith("data:"):
            raise ValueError("Ollama image parts must use a base64 data URL")
        header, separator, encoded_image = image_url.partition(",")
        if not separator or ";base64" not in header:
            raise ValueError("Ollama image parts must use a base64 data URL")
        images.append(encoded_image)
    return images


def _error_message(response_body: bytes) -> str | None:
    try:
        error_data = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        message = response_body.decode("utf-8", errors="replace").strip()
    else:
        message = error_data.get("error") if isinstance(error_data, dict) else None
    if not isinstance(message, str):
        return None
    message = " ".join(message.split())
    return message[:500] if message else None