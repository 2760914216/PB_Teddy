from __future__ import annotations


def format_recovery_message(error: Exception) -> str:
    code = getattr(error, "code", "runtime_error")
    message = getattr(error, "message", str(error))
    recovery_hint = getattr(
        error, "recovery_hint", "请检查输入、数据库与模型状态后重试。"
    )
    return f"[{code}] {message}。建议：{recovery_hint}"
