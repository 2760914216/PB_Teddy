from __future__ import annotations

import importlib
import json
import urllib.error
import urllib.request
from collections.abc import Callable

from .config import OllamaConfig, Task2Config, load_task2_config


def _strip_json_fence(payload: str) -> str:
    cleaned = payload.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("json\n", "", 1)
    return cleaned.strip()


class Task2LLMClient:
    config: Task2Config
    transport: Callable[[dict[str, object]], dict[str, object]] | None

    def __init__(
        self,
        config: str | Task2Config = "config.yaml",
        transport: Callable[[dict[str, object]], dict[str, object]] | None = None,
        model_override: str | None = None,
    ) -> None:
        self.config = load_task2_config(config) if isinstance(config, str) else config
        if model_override:
            object.__setattr__(
                self.config,
                "ollama",
                OllamaConfig(
                    host=self.config.ollama.host,
                    model=model_override,
                    timeout_seconds=self.config.ollama.timeout_seconds,
                    temperature=self.config.ollama.temperature,
                    max_retries=self.config.ollama.max_retries,
                ),
            )
        self.transport = transport

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        schema_hint: dict[str, object] | None = None,
    ) -> dict[str, object]:
        payload = {
            "model": self.config.ollama.model,
            "stream": False,
            "format": "json",
            "options": {"temperature": self.config.ollama.temperature},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if schema_hint:
            payload["schema_hint"] = schema_hint

        last_error: Exception | None = None
        attempts = max(1, self.config.ollama.max_retries + 1)
        for _ in range(attempts):
            try:
                response = self._send(payload)
                content = self._extract_message_content(response)
                return self._decode_json(content)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        raise self._task2_error(
            "ModelResponseError",
            f"模型未返回可解析 JSON: {last_error}",
        )

    def _send(self, payload: dict[str, object]) -> dict[str, object]:
        if self.transport is not None:
            return self.transport(payload)

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url=f"{self.config.ollama.host}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.config.ollama.timeout_seconds,
            ) as response:
                raw_response = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise self._task2_error(
                "ModelResponseError", f"无法连接 Ollama: {exc}"
            ) from exc
        return self._decode_json(raw_response)

    def _extract_message_content(self, response: dict[str, object]) -> str:
        message = response.get("message")
        if not isinstance(message, dict):
            raise self._task2_error("ModelResponseError", "模型响应缺少 message 字段")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise self._task2_error("ModelResponseError", "模型响应 content 为空")
        return content

    def _decode_json(self, payload: str) -> dict[str, object]:
        cleaned = _strip_json_fence(payload)
        try:
            decoded = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise self._task2_error(
                "ModelResponseError", f"JSON 解析失败: {exc}"
            ) from exc
        if not isinstance(decoded, dict):
            raise self._task2_error("ModelResponseError", "模型响应不是 JSON 对象")
        return decoded

    def _task2_error(self, class_name: str, message: str) -> Exception:
        errors_module = importlib.import_module("src.task2.errors")
        error_class = getattr(errors_module, class_name)
        return error_class(message)
