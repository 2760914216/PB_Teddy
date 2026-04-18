from __future__ import annotations

import importlib
from dataclasses import replace
from typing import cast

from .config import OllamaConfig, Task2Config, load_task2_config
from .errors import IntentJudgeError
from .llm_client import Task2LLMClient

ALLOWED_STATUSES = {"resolved", "clarify", "abstain"}
ALLOWED_SLOT_UPDATE_KEYS = {
    "stock_code",
    "stock_abbr",
    "metric_name",
    "metric_column",
    "table_name",
}


def _abstain_result(
    reason: str, *, source: str, error: str | None = None
) -> dict[str, object]:
    result: dict[str, object] = {
        "status": "abstain",
        "confidence": 0.0,
        "clarification_question": None,
        "reason": reason,
        "slot_updates": {},
        "source": source,
    }
    if error:
        result["error"] = error
    return result


def _judge_enabled(config: Task2Config, *, use_llm: bool) -> bool:
    return use_llm and config.task2.judge_enabled


def _candidate_metric_keys(
    resolved_context: dict[str, object],
) -> set[tuple[str, str, str]]:
    candidates = cast(
        list[dict[str, object]], resolved_context.get("metric_candidates") or []
    )
    keys = {
        (
            str(item.get("name") or ""),
            str(item.get("column") or ""),
            str(item.get("table") or ""),
        )
        for item in candidates
        if item.get("name") and item.get("column") and item.get("table")
    }
    if (
        not keys
        and resolved_context.get("metric_name")
        and resolved_context.get("metric_column")
    ):
        keys.add(
            (
                str(resolved_context.get("metric_name") or ""),
                str(resolved_context.get("metric_column") or ""),
                str(resolved_context.get("table_name") or ""),
            )
        )
    return keys


def _candidate_company_keys(
    resolved_context: dict[str, object],
) -> set[tuple[str, str]]:
    candidates = cast(
        list[dict[str, object]], resolved_context.get("company_candidates") or []
    )
    keys = {
        (str(item.get("stock_code") or ""), str(item.get("stock_abbr") or ""))
        for item in candidates
        if item.get("stock_code") or item.get("stock_abbr")
    }
    if not keys and (
        resolved_context.get("stock_code") or resolved_context.get("stock_abbr")
    ):
        keys.add(
            (
                str(resolved_context.get("stock_code") or ""),
                str(resolved_context.get("stock_abbr") or ""),
            )
        )
    return keys


def _normalize_status(raw_status: object) -> str:
    status = str(raw_status or "abstain").strip().lower()
    if status not in ALLOWED_STATUSES:
        raise IntentJudgeError(f"非法 judge 状态: {status}")
    return status


def _normalize_confidence(raw_confidence: object) -> float:
    if raw_confidence is None:
        return 0.0
    if isinstance(raw_confidence, bool):
        return float(raw_confidence)
    if isinstance(raw_confidence, (int, float, str)):
        confidence = float(raw_confidence)
        return max(0.0, min(1.0, confidence))
    raise IntentJudgeError(f"非法 judge 置信度: {raw_confidence!r}")


def _normalize_clarification_question(
    payload: dict[str, object], status: str
) -> str | None:
    question = payload.get("clarification_question")
    if question is None:
        return None
    text = str(question).strip()
    if not text:
        return None
    if status == "clarify":
        return text
    return None


def _validate_slot_updates(
    payload: dict[str, object], resolved_context: dict[str, object]
) -> dict[str, object]:
    raw_slot_updates = payload.get("slot_updates") or {}
    if not isinstance(raw_slot_updates, dict):
        raise IntentJudgeError("judge slot_updates 不是对象")
    unexpected = set(raw_slot_updates) - ALLOWED_SLOT_UPDATE_KEYS
    if unexpected:
        raise IntentJudgeError(f"judge 返回了未允许的字段: {sorted(unexpected)}")

    cleaned: dict[str, object] = {}
    company_keys = _candidate_company_keys(resolved_context)
    metric_keys = _candidate_metric_keys(resolved_context)

    stock_code = raw_slot_updates.get("stock_code")
    stock_abbr = raw_slot_updates.get("stock_abbr")
    if stock_code is not None or stock_abbr is not None:
        company_key = (str(stock_code or ""), str(stock_abbr or ""))
        if company_key not in company_keys:
            raise IntentJudgeError("judge 选择的公司不在候选集中")
        cleaned["stock_code"] = company_key[0] or None
        cleaned["stock_abbr"] = company_key[1] or None

    metric_name = raw_slot_updates.get("metric_name")
    metric_column = raw_slot_updates.get("metric_column")
    table_name = raw_slot_updates.get("table_name")
    if metric_name is not None or metric_column is not None or table_name is not None:
        metric_key = (
            str(metric_name or ""),
            str(metric_column or ""),
            str(table_name or ""),
        )
        if metric_key not in metric_keys:
            raise IntentJudgeError("judge 选择的指标不在候选集中")
        cleaned["metric_name"] = metric_key[0] or None
        cleaned["metric_column"] = metric_key[1] or None
        cleaned["table_name"] = metric_key[2] or None
    return cleaned


def _normalize_judge_payload(
    payload: dict[str, object],
    resolved_context: dict[str, object],
    config: Task2Config,
) -> dict[str, object]:
    status = _normalize_status(payload.get("status"))
    confidence = _normalize_confidence(payload.get("confidence"))
    if confidence < config.task2.judge_confidence_threshold:
        return _abstain_result(
            f"judge 置信度过低: {confidence:.2f}",
            source="judge_low_confidence",
        )
    slot_updates = _validate_slot_updates(payload, resolved_context)
    clarification_question = _normalize_clarification_question(payload, status)
    reason = str(payload.get("reason") or "judge 已完成裁决").strip()
    if status == "clarify" and not clarification_question:
        raise IntentJudgeError("judge 要求澄清但未提供中文追问")
    if status == "resolved" and not slot_updates:
        raise IntentJudgeError("judge 标记为 resolved 但没有有效 slot_updates")
    return {
        "status": status,
        "confidence": confidence,
        "clarification_question": clarification_question,
        "reason": reason,
        "slot_updates": slot_updates,
        "source": "judge",
    }


def _build_judge_client(
    config: Task2Config,
    transport: object | None,
) -> Task2LLMClient:
    judge_config = replace(
        config,
        ollama=OllamaConfig(
            host=config.ollama.host,
            model=config.ollama.model,
            timeout_seconds=config.task2.judge_timeout_seconds,
            temperature=config.ollama.temperature,
            max_retries=config.task2.judge_max_retries,
        ),
    )
    typed_transport = cast(
        "callable[[dict[str, object]], dict[str, object]] | None", transport
    )
    return Task2LLMClient(judge_config, transport=typed_transport)


def run_intent_judge(
    question: str,
    resolved_context: dict[str, object],
    config: str | Task2Config = "config.yaml",
    *,
    use_llm: bool = True,
    transport: object | None = None,
) -> dict[str, object]:
    loaded_config = load_task2_config(config) if isinstance(config, str) else config
    if not _judge_enabled(loaded_config, use_llm=use_llm):
        return _abstain_result("judge 已禁用", source="judge_disabled")
    if not bool(resolved_context.get("judge_needed")):
        return _abstain_result("规则已足够明确", source="judge_skipped")

    prompts_module = importlib.import_module("src.task2.prompts_judge")
    build_prompt = getattr(prompts_module, "build_intent_judge_prompt")
    system_prompt, user_prompt, schema_hint = build_prompt(question, resolved_context)
    client = _build_judge_client(loaded_config, transport)
    try:
        payload = client.chat_json(
            system_prompt,
            user_prompt,
            schema_hint=schema_hint,
        )
        return _normalize_judge_payload(payload, resolved_context, loaded_config)
    except Exception as exc:  # noqa: BLE001
        return _abstain_result(
            "judge 执行失败，已回退到规则澄清",
            source="judge_fallback",
            error=str(exc),
        )
