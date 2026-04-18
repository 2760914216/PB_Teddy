from __future__ import annotations

import importlib
from typing import cast

from .config import Task2Config, load_task2_config


def llm_clarify_if_needed(
    question: str,
    resolved_context: dict[str, object],
    config: Task2Config | str = "config.yaml",
) -> dict[str, object]:
    """LLM-driven intent clarification - replaces hardcoded rules.

    Args:
        question: Original user question.
        resolved_context: Parsed context from resolver.
        config: Config path or Task2Config instance.

    Returns:
        dict with keys: needs_clarification, question, missing_fields, reason.
    """
    loaded_config = load_task2_config(config) if isinstance(config, str) else config

    prompts_module = importlib.import_module("src.task2.prompts_nl2sql")
    llm_module = importlib.import_module("src.task2.llm_client")
    build_clarification_prompt = getattr(prompts_module, "build_clarification_prompt")
    llm_client_class = getattr(llm_module, "Task2LLMClient")

    client = llm_client_class(loaded_config)
    system_prompt, user_prompt = build_clarification_prompt(
        question, resolved_context, loaded_config
    )

    try:
        llm_output = client.chat_json(system_prompt, user_prompt)
    except Exception:
        return {
            "needs_clarification": False,
            "question": None,
            "missing_fields": [],
            "reason": "LLM调用失败，回退到下一阶段",
        }

    needs_clarification = bool(llm_output.get("needs_clarification", False))
    clarification_question = str(llm_output.get("question") or "")
    raw_missing_fields = llm_output.get("missing_fields") or []
    missing_fields = [str(item) for item in raw_missing_fields]

    if needs_clarification and not clarification_question:
        clarification_question = "请补充查询所需信息。"

    if needs_clarification:
        return {
            "needs_clarification": True,
            "question": clarification_question,
            "missing_fields": missing_fields,
            "reason": "LLM判断需要澄清",
        }

    return {
        "needs_clarification": False,
        "question": None,
        "missing_fields": [],
        "reason": "LLM判断信息完整",
    }


def clarify_if_needed(resolved_context: dict[str, object]) -> dict[str, object]:
    raw_missing_fields = cast(
        list[object], resolved_context.get("missing_fields") or []
    )
    missing_fields = [str(item) for item in raw_missing_fields]
    metric_name = str(resolved_context.get("metric_name") or "该指标")
    intent = str(resolved_context.get("intent") or "single_value")
    recent_years = resolved_context.get("recent_years")

    if "missing_company" in missing_fields:
        return {
            "needs_clarification": True,
            "question": "请说明要查询的公司名称或股票代码。",
            "missing_fields": ["missing_company"],
            "reason": "缺少公司信息",
        }

    if "missing_metric" in missing_fields:
        return {
            "needs_clarification": True,
            "question": "请说明想查询的财务指标，例如利润总额、净利润或营业收入。",
            "missing_fields": ["missing_metric"],
            "reason": "缺少财务指标",
        }

    if "missing_report_period" in missing_fields:
        return {
            "needs_clarification": True,
            "question": f"请问你查询哪一个报告期的{metric_name}？例如 2025 年第三季度或 2024 年年报。",
            "missing_fields": ["missing_report_period"],
            "reason": "缺少报告期",
        }

    if intent == "trend" and isinstance(recent_years, int):
        return {
            "needs_clarification": False,
            "question": None,
            "missing_fields": [],
            "defaulted_range": f"默认按近 {recent_years} 个年度/最新报告期理解",
            "reason": "模糊时间范围已按默认策略解释",
        }

    return {
        "needs_clarification": False,
        "question": None,
        "missing_fields": [],
        "reason": "信息完整，可继续生成查询计划",
    }
