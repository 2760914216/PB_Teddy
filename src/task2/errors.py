from __future__ import annotations


class Task2Error(Exception):
    code: str
    message: str
    recovery_hint: str
    details: dict[str, object]

    def __init__(
        self,
        code: str,
        message: str,
        recovery_hint: str = "",
        details: dict[str, object] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.recovery_hint = recovery_hint
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "code": self.code,
            "message": self.message,
        }
        if self.recovery_hint:
            payload["recovery_hint"] = self.recovery_hint
        if self.details:
            payload["details"] = self.details
        return payload


class ConfigError(Task2Error):
    def __init__(
        self, message: str, recovery_hint: str = "请检查 config.yaml 配置。"
    ) -> None:
        super().__init__("config_error", message, recovery_hint)


class PreflightError(Task2Error):
    def __init__(
        self, message: str, recovery_hint: str = "请先通过预检后再启动任务2。"
    ) -> None:
        super().__init__("preflight_failed", message, recovery_hint)


class ModelResponseError(Task2Error):
    def __init__(
        self,
        message: str,
        recovery_hint: str = "请检查 Ollama 服务、模型名或稍后重试。",
    ) -> None:
        super().__init__("model_response_error", message, recovery_hint)


class SQLGuardrailError(Task2Error):
    def __init__(
        self,
        message: str,
        recovery_hint: str = "请改问查询类问题，并避免写入或危险 SQL。",
    ) -> None:
        super().__init__("sql_guardrail_blocked", message, recovery_hint)


class DBExecutionError(Task2Error):
    def __init__(
        self, message: str, recovery_hint: str = "请确认数据库可连接且查询语句有效。"
    ) -> None:
        super().__init__("db_execution_error", message, recovery_hint)


class NoDataError(Task2Error):
    def __init__(
        self, message: str, recovery_hint: str = "请换一个公司、报告期或财务指标再试。"
    ) -> None:
        super().__init__("no_data", message, recovery_hint)


class ExportError(Task2Error):
    def __init__(
        self, message: str, recovery_hint: str = "请检查 result/ 目录写权限和导出依赖。"
    ) -> None:
        super().__init__("export_error", message, recovery_hint)
