from __future__ import annotations

from typing import cast


def _as_str_list(value: object) -> list[str]:
    return [str(item) for item in cast(list[object], value or [])]


def _metric_candidate_names(resolved_context: dict[str, object]) -> list[str]:
    candidates = cast(
        list[dict[str, object]], resolved_context.get("metric_candidates") or []
    )
    names: list[str] = []
    for item in candidates:
        name = str(item.get("name") or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def _company_candidate_names(resolved_context: dict[str, object]) -> list[str]:
    candidates = cast(
        list[dict[str, object]], resolved_context.get("company_candidates") or []
    )
    names: list[str] = []
    for item in candidates:
        name = str(item.get("stock_abbr") or item.get("stock_code") or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def precheck_required_fields(resolved_context: dict[str, object]) -> dict[str, object]:
    missing_fields = _as_str_list(resolved_context.get("missing_fields"))
    if "missing_company" in missing_fields and not resolved_context.get(
        "company_candidates"
    ):
        return {
            "needs_clarification": True,
            "question": "请说明要查询的公司名称或股票代码。",
            "missing_fields": ["missing_company"],
            "reason": "缺少公司信息",
            "final_context": dict(resolved_context),
        }

    if "missing_metric" in missing_fields and not resolved_context.get(
        "metric_candidates"
    ):
        return {
            "needs_clarification": True,
            "question": "请说明想查询的财务指标，例如利润总额、净利润或营业收入。",
            "missing_fields": ["missing_metric"],
            "reason": "缺少财务指标",
            "final_context": dict(resolved_context),
        }

    return {
        "needs_clarification": False,
        "question": None,
        "missing_fields": [],
        "reason": "基础必填槽位已满足或存在候选",
        "final_context": dict(resolved_context),
    }


def _apply_judge_updates(
    resolved_context: dict[str, object], judge_result: dict[str, object] | None
) -> dict[str, object]:
    final_context = dict(resolved_context)
    if not judge_result or str(judge_result.get("status") or "abstain") != "resolved":
        return final_context

    slot_updates = cast(dict[str, object], judge_result.get("slot_updates") or {})
    if not slot_updates:
        return final_context

    for key, value in slot_updates.items():
        final_context[key] = value

    missing_fields = _as_str_list(final_context.get("missing_fields"))
    ambiguity_flags = _as_str_list(final_context.get("ambiguity_flags"))
    if {"metric_name", "metric_column", "table_name"} & set(slot_updates):
        missing_fields = [item for item in missing_fields if item != "missing_metric"]
        ambiguity_flags = [
            item for item in ambiguity_flags if item != "ambiguous_metric"
        ]
        final_context["metric_candidates"] = [
            {
                "name": str(final_context.get("metric_name") or ""),
                "column": str(final_context.get("metric_column") or ""),
                "table": str(final_context.get("table_name") or ""),
                "matched_term": "judge",
            }
        ]
    if {"stock_code", "stock_abbr"} & set(slot_updates):
        missing_fields = [item for item in missing_fields if item != "missing_company"]
        ambiguity_flags = [
            item for item in ambiguity_flags if item != "ambiguous_company"
        ]
        final_context["company_candidates"] = [
            {
                "stock_code": str(final_context.get("stock_code") or ""),
                "stock_abbr": str(final_context.get("stock_abbr") or ""),
            }
        ]
    final_context["missing_fields"] = missing_fields
    final_context["ambiguity_flags"] = ambiguity_flags
    final_context["judge_needed"] = bool(ambiguity_flags)
    return final_context


def finalize_clarification(
    resolved_context: dict[str, object],
    judge_result: dict[str, object] | None = None,
) -> dict[str, object]:
    final_context = _apply_judge_updates(resolved_context, judge_result)
    missing_fields = _as_str_list(final_context.get("missing_fields"))
    ambiguity_flags = _as_str_list(final_context.get("ambiguity_flags"))
    metric_name = str(final_context.get("metric_name") or "该指标")
    intent = str(final_context.get("intent") or "single_value")
    recent_years = final_context.get("recent_years")

    judge_status = str((judge_result or {}).get("status") or "abstain")
    if judge_status == "clarify":
        clarification_question = str(
            (judge_result or {}).get("clarification_question")
            or "请补充更明确的查询信息。"
        )
        return {
            "needs_clarification": True,
            "question": clarification_question,
            "missing_fields": missing_fields,
            "reason": str((judge_result or {}).get("reason") or "judge 请求澄清"),
            "final_context": final_context,
        }

    if "ambiguous_company" in ambiguity_flags:
        candidate_names = "、".join(_company_candidate_names(final_context)[:3])
        prompt = "请说明你要查询的具体公司名称或股票代码。"
        if candidate_names:
            prompt = f"请确认你要查询的公司，是 {candidate_names} 中的哪一家？"
        return {
            "needs_clarification": True,
            "question": prompt,
            "missing_fields": missing_fields,
            "reason": "公司存在歧义",
            "final_context": final_context,
        }

    if "ambiguous_metric" in ambiguity_flags:
        candidate_names = "、".join(_metric_candidate_names(final_context)[:4])
        prompt = "请说明你想查询的财务指标。"
        if candidate_names:
            prompt = f"请确认你想查询的是 {candidate_names} 中的哪一个指标？"
        return {
            "needs_clarification": True,
            "question": prompt,
            "missing_fields": missing_fields,
            "reason": "财务指标存在歧义",
            "final_context": final_context,
        }

    if "missing_report_period" in missing_fields:
        return {
            "needs_clarification": True,
            "question": f"请问你查询哪一个报告期的{metric_name}？例如 2025 年第三季度或 2024 年年报。",
            "missing_fields": ["missing_report_period"],
            "reason": "缺少报告期",
            "final_context": final_context,
        }

    if intent == "trend" and isinstance(recent_years, int):
        return {
            "needs_clarification": False,
            "question": None,
            "missing_fields": [],
            "defaulted_range": f"默认按近 {recent_years} 个年度/最新报告期理解",
            "reason": "模糊时间范围已按默认策略解释",
            "final_context": final_context,
        }

    return {
        "needs_clarification": False,
        "question": None,
        "missing_fields": [],
        "reason": "信息完整，可继续生成查询计划",
        "final_context": final_context,
    }


def clarify_if_needed(
    resolved_context: dict[str, object],
    judge_result: dict[str, object] | None = None,
) -> dict[str, object]:
    precheck = precheck_required_fields(resolved_context)
    if bool(precheck.get("needs_clarification")):
        return precheck
    return finalize_clarification(resolved_context, judge_result)
