from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path
from typing import cast

import pymysql

from .config import Task2Config, load_task2_config

METRIC_CATALOG: tuple[dict[str, object], ...] = (
    {
        "name": "利润总额",
        "column": "total_profit",
        "table": "income_sheet",
        "aliases": ("利润总额", "利润"),
    },
    {
        "name": "净利润",
        "column": "net_profit",
        "table": "income_sheet",
        "aliases": ("净利润", "归母净利润", "归母净利", "净利", "利润"),
    },
    {
        "name": "营业总收入",
        "column": "total_operating_revenue",
        "table": "income_sheet",
        "aliases": ("营业总收入", "营业收入", "营收"),
    },
    {
        "name": "营业收入",
        "column": "total_operating_revenue",
        "table": "income_sheet",
        "aliases": ("营业收入", "营收"),
    },
    {
        "name": "营业利润",
        "column": "operating_profit",
        "table": "income_sheet",
        "aliases": ("营业利润", "经营利润", "经营性利润", "利润"),
    },
    {
        "name": "每股收益",
        "column": "eps",
        "table": "core_performance_indicators_sheet",
        "aliases": ("每股收益", "每股盈利"),
    },
    {
        "name": "基本每股收益",
        "column": "eps",
        "table": "core_performance_indicators_sheet",
        "aliases": ("基本每股收益",),
    },
    {
        "name": "净资产收益率",
        "column": "roe",
        "table": "core_performance_indicators_sheet",
        "aliases": ("净资产收益率", "ROE", "roe"),
    },
    {
        "name": "ROE",
        "column": "roe",
        "table": "core_performance_indicators_sheet",
        "aliases": ("ROE", "roe"),
    },
    {
        "name": "资产总计",
        "column": "asset_total_assets",
        "table": "balance_sheet",
        "aliases": ("资产总计", "总资产", "资产规模"),
    },
    {
        "name": "总资产",
        "column": "asset_total_assets",
        "table": "balance_sheet",
        "aliases": ("总资产", "资产总额"),
    },
    {
        "name": "负债合计",
        "column": "liability_total_liabilities",
        "table": "balance_sheet",
        "aliases": ("负债合计", "总负债"),
    },
    {
        "name": "总负债",
        "column": "liability_total_liabilities",
        "table": "balance_sheet",
        "aliases": ("总负债",),
    },
    {
        "name": "资产负债率",
        "column": "asset_liability_ratio",
        "table": "balance_sheet",
        "aliases": ("资产负债率", "负债率"),
    },
    {
        "name": "现金及现金等价物净增加额",
        "column": "net_cash_flow",
        "table": "cash_flow_sheet",
        "aliases": ("现金及现金等价物净增加额", "现金净增加额", "净现金流"),
    },
    {
        "name": "现金净增加额",
        "column": "net_cash_flow",
        "table": "cash_flow_sheet",
        "aliases": ("现金净增加额", "净现金流"),
    },
)

TREND_KEYWORDS = ("趋势", "变化", "走势", "波动", "变动")
FOLLOW_UP_PREFIXES = (
    "那",
    "那么",
    "它",
    "他",
    "她",
    "这",
    "这个",
    "该",
    "其中",
    "前者",
    "后者",
)


def _normalize_question(question: str) -> str:
    return re.sub(r"\s+", "", question).strip()


def _quarter_suffix(raw_text: str) -> str:
    matched = raw_text.upper()
    if "Q1" in matched or "第一季度" in raw_text or "一季度" in raw_text:
        return "Q1"
    if "Q2" in matched or "第二季度" in raw_text or "二季度" in raw_text:
        return "Q2"
    if (
        "Q3" in matched
        or "第三季度" in raw_text
        or "三季度" in raw_text
        or "前三季度" in raw_text
    ):
        return "Q3"
    if "HY" in matched or "H1" in matched or "半年" in raw_text or "中报" in raw_text:
        return "HY"
    if (
        "FY" in matched
        or "年度" in raw_text
        or "年报" in raw_text
        or "全年" in raw_text
    ):
        return "FY"
    return ""


def _parse_explicit_period(question: str) -> tuple[str | None, int | None]:
    explicit = re.search(
        r"(20\d{2})\s*(?:年)?\s*(Q[1-4]|H1|HY|FY|第一季度|第二季度|第三季度|一季度|二季度|三季度|前三季度|半年报|半年|中报|年报|年度|全年)",
        question,
        re.IGNORECASE,
    )
    if explicit:
        year = int(explicit.group(1))
        suffix = _quarter_suffix(explicit.group(2))
        if suffix:
            return f"{year}{suffix}", year

    year_only = re.search(r"(20\d{2})\s*年", question)
    if year_only and any(keyword in question for keyword in ("年报", "年度", "全年")):
        year = int(year_only.group(1))
        return f"{year}FY", year
    return None, None


def _parse_recent_years(question: str, default_recent_years: int) -> int | None:
    if "近几年" in question or "近年" in question:
        return default_recent_years
    matched = re.search(r"近([一二两三四五六七八九十\d]+)年", question)
    if not matched:
        return None
    raw_value = matched.group(1)
    chinese_digits = {
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }
    if raw_value.isdigit():
        return max(2, int(raw_value))
    return max(2, chinese_digits.get(raw_value, default_recent_years))


def _infer_intent(question: str) -> str:
    return (
        "trend"
        if any(keyword in question for keyword in TREND_KEYWORDS)
        else "single_value"
    )


def _metric_key(metric: dict[str, object]) -> tuple[str, str]:
    return str(metric["table"]), str(metric["column"])


def _dedupe_metric_candidates(
    matches: list[tuple[dict[str, object], str]],
) -> list[dict[str, str]]:
    grouped: dict[tuple[str, str], dict[str, object]] = {}
    for metric, matched_term in matches:
        key = _metric_key(metric)
        current = grouped.get(key)
        if current is None or len(matched_term) > len(str(current["matched_term"])):
            grouped[key] = {"metric": metric, "matched_term": matched_term}
    if not grouped:
        return []
    max_term_length = max(len(str(item["matched_term"])) for item in grouped.values())
    candidates: list[dict[str, str]] = []
    for item in grouped.values():
        matched_term = str(item["matched_term"])
        if len(matched_term) != max_term_length:
            continue
        metric = cast(dict[str, object], item["metric"])
        candidates.append(
            {
                "name": str(metric["name"]),
                "column": str(metric["column"]),
                "table": str(metric["table"]),
                "matched_term": matched_term,
            }
        )
    return sorted(
        candidates, key=lambda item: (item["table"], item["column"], item["name"])
    )


def _infer_metric(question: str) -> dict[str, object]:
    ranked = sorted(
        METRIC_CATALOG, key=lambda item: len(str(item["name"])), reverse=True
    )
    matches: list[tuple[dict[str, object], str]] = []
    for metric in ranked:
        aliases = tuple(
            str(item) for item in cast(tuple[object, ...], metric["aliases"])
        )
        for alias in aliases:
            if alias and alias in question:
                matches.append((metric, alias))
    candidates = _dedupe_metric_candidates(matches)
    selected = candidates[0] if len(candidates) == 1 else None
    return {
        "selected": selected,
        "candidates": candidates,
        "ambiguous": len(candidates) > 1,
    }


def _load_company_catalog_from_csv(root_dir: Path) -> list[dict[str, str]]:
    csv_path = root_dir / "ex_db_result" / "income_sheet.csv"
    if not csv_path.exists():
        return []
    seen: set[tuple[str, str]] = set()
    rows: list[dict[str, str]] = []
    with csv_path.open("r", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            stock_code = (row.get("stock_code") or "").strip()
            stock_abbr = (row.get("stock_abbr") or "").strip()
            if not stock_code or not stock_abbr:
                continue
            key = (stock_code, stock_abbr)
            if key in seen:
                continue
            seen.add(key)
            rows.append({"stock_code": stock_code, "stock_abbr": stock_abbr})
    return rows


@lru_cache(maxsize=8)
def _load_company_catalog(config_path: str) -> tuple[tuple[str, str], ...]:
    config = load_task2_config(config_path)
    try:
        connection = pymysql.connect(
            host=config.database.host,
            port=config.database.port,
            user=config.database.user,
            password=config.database.password,
            database=config.database.database,
            cursorclass=pymysql.cursors.DictCursor,
            charset="utf8mb4",
            autocommit=True,
        )
        try:
            with connection.cursor() as cursor:
                _ = cursor.execute(
                    "SELECT DISTINCT stock_code, stock_abbr FROM income_sheet ORDER BY stock_code"
                )
                rows: list[dict[str, object]] = [dict(row) for row in cursor.fetchall()]
        finally:
            connection.close()
        return tuple(
            (str(row.get("stock_code", "")), str(row.get("stock_abbr", "")))
            for row in rows
            if row.get("stock_code") and row.get("stock_abbr")
        )
    except Exception:
        fallback_rows = _load_company_catalog_from_csv(config.root_dir)
        return tuple((row["stock_code"], row["stock_abbr"]) for row in fallback_rows)


def _resolve_company(question: str, config: Task2Config) -> dict[str, object]:
    catalog = _load_company_catalog(str(config.config_path))
    name_matches = [
        {"stock_code": stock_code, "stock_abbr": stock_abbr, "matched_term": stock_abbr}
        for stock_code, stock_abbr in catalog
        if stock_abbr and stock_abbr in question
    ]
    if name_matches:
        max_term_length = max(len(item["matched_term"]) for item in name_matches)
        candidates = [
            {"stock_code": item["stock_code"], "stock_abbr": item["stock_abbr"]}
            for item in name_matches
            if len(item["matched_term"]) == max_term_length
        ]
        selected = candidates[0] if len(candidates) == 1 else None
        return {
            "selected": selected,
            "candidates": candidates,
            "ambiguous": len(candidates) > 1,
        }

    code_match = re.search(r"\b(\d{6})\b", question)
    if code_match:
        code = code_match.group(1)
        for stock_code, stock_abbr in catalog:
            if stock_code == code:
                return {
                    "selected": {"stock_code": stock_code, "stock_abbr": stock_abbr},
                    "candidates": [
                        {"stock_code": stock_code, "stock_abbr": stock_abbr}
                    ],
                    "ambiguous": False,
                }
        return {
            "selected": {"stock_code": code, "stock_abbr": ""},
            "candidates": [{"stock_code": code, "stock_abbr": ""}],
            "ambiguous": False,
        }

    return {"selected": None, "candidates": [], "ambiguous": False}


def _looks_like_follow_up(
    question: str,
    previous_context: dict[str, object],
    *,
    has_company: bool,
    has_metric: bool,
    has_period: bool,
) -> bool:
    if not previous_context:
        return False
    previous_missing_fields = {
        str(item)
        for item in cast(list[object], previous_context.get("missing_fields") or [])
        if item is not None
    }
    if previous_missing_fields:
        return True
    if question.startswith(FOLLOW_UP_PREFIXES):
        return True
    if question.endswith("的") or question.endswith("呢"):
        return True
    known_slots = sum(1 for value in (has_company, has_metric, has_period) if value)
    return len(question) <= 16 and known_slots <= 1


def _carry_company(
    company: dict[str, object],
    previous_context: dict[str, object],
    *,
    allow_follow_up: bool,
    carry_applied: list[str],
) -> dict[str, object]:
    selected = company.get("selected")
    if isinstance(selected, dict) and (
        selected.get("stock_code") or selected.get("stock_abbr")
    ):
        return company
    previous_missing_fields = {
        str(item)
        for item in cast(list[object], previous_context.get("missing_fields") or [])
        if item is not None
    }
    should_carry = "missing_company" in previous_missing_fields or allow_follow_up
    if not should_carry:
        return company
    previous_stock_code = previous_context.get("stock_code")
    previous_stock_abbr = previous_context.get("stock_abbr")
    if not isinstance(previous_stock_code, str) and not isinstance(
        previous_stock_abbr, str
    ):
        return company
    carry_applied.append("company")
    carried = {
        "stock_code": previous_stock_code
        if isinstance(previous_stock_code, str)
        else "",
        "stock_abbr": previous_stock_abbr
        if isinstance(previous_stock_abbr, str)
        else "",
    }
    return {"selected": carried, "candidates": [carried], "ambiguous": False}


def _carry_metric(
    metric_result: dict[str, object],
    previous_context: dict[str, object],
    *,
    allow_follow_up: bool,
    carry_applied: list[str],
) -> dict[str, object]:
    selected = metric_result.get("selected")
    if isinstance(selected, dict) and selected.get("column") and selected.get("table"):
        return metric_result
    previous_missing_fields = {
        str(item)
        for item in cast(list[object], previous_context.get("missing_fields") or [])
        if item is not None
    }
    should_carry = "missing_metric" in previous_missing_fields or allow_follow_up
    if not should_carry:
        return metric_result
    previous_metric_name = previous_context.get("metric_name")
    previous_metric_column = previous_context.get("metric_column")
    previous_table_name = previous_context.get("table_name")
    if not isinstance(previous_metric_name, str) or not isinstance(
        previous_metric_column, str
    ):
        return metric_result
    carry_applied.append("metric")
    carried = {
        "name": previous_metric_name,
        "column": previous_metric_column,
        "table": str(previous_table_name or ""),
        "matched_term": "previous_context",
    }
    return {"selected": carried, "candidates": [carried], "ambiguous": False}


def _carry_period(
    report_period: str | None,
    report_year: int | None,
    question: str,
    previous_context: dict[str, object],
    *,
    allow_follow_up: bool,
    carry_applied: list[str],
) -> tuple[str | None, int | None]:
    if report_period is not None:
        return report_period, report_year
    previous_missing_fields = {
        str(item)
        for item in cast(list[object], previous_context.get("missing_fields") or [])
        if item is not None
    }
    should_carry = "missing_report_period" in previous_missing_fields or allow_follow_up
    if not should_carry or re.search(r"20\d{2}", question):
        return report_period, report_year
    previous_period = previous_context.get("report_period")
    if not isinstance(previous_period, str):
        return report_period, report_year
    carry_applied.append("report_period")
    previous_year = previous_context.get("report_year")
    carried_year = previous_year if isinstance(previous_year, int) else report_year
    return previous_period, carried_year


def _resolver_confidence(
    *,
    missing_fields: list[str],
    ambiguity_flags: list[str],
    carry_applied: list[str],
) -> float:
    if ambiguity_flags:
        return 0.45
    if missing_fields:
        return 0.6 if len(missing_fields) == 1 else 0.4
    if carry_applied:
        return 0.85
    return 1.0


def resolve_question_context(
    question: str,
    config: str | Task2Config = "config.yaml",
    previous_context: dict[str, object] | None = None,
) -> dict[str, object]:
    loaded_config = load_task2_config(config) if isinstance(config, str) else config
    normalized_question = _normalize_question(question)
    previous = previous_context or {}

    company = _resolve_company(normalized_question, loaded_config)
    metric_result = _infer_metric(normalized_question)
    report_period, report_year = _parse_explicit_period(normalized_question)

    allow_follow_up = _looks_like_follow_up(
        normalized_question,
        previous,
        has_company=bool(company.get("selected")),
        has_metric=bool(metric_result.get("selected")),
        has_period=report_period is not None,
    )
    carry_applied: list[str] = []
    company = _carry_company(
        company,
        previous,
        allow_follow_up=allow_follow_up,
        carry_applied=carry_applied,
    )
    metric_result = _carry_metric(
        metric_result,
        previous,
        allow_follow_up=allow_follow_up,
        carry_applied=carry_applied,
    )
    report_period, report_year = _carry_period(
        report_period,
        report_year,
        normalized_question,
        previous,
        allow_follow_up=allow_follow_up,
        carry_applied=carry_applied,
    )

    intent = _infer_intent(normalized_question)
    recent_years = _parse_recent_years(
        normalized_question, loaded_config.task2.default_recent_years
    )
    if recent_years is None and intent == "trend" and allow_follow_up:
        previous_recent_years = previous.get("recent_years")
        if isinstance(previous_recent_years, int):
            recent_years = previous_recent_years

    selected_company = cast(dict[str, str] | None, company.get("selected"))
    selected_metric = cast(dict[str, str] | None, metric_result.get("selected"))
    company_candidates = cast(list[dict[str, str]], company.get("candidates") or [])
    metric_candidates = cast(
        list[dict[str, str]], metric_result.get("candidates") or []
    )

    missing_fields: list[str] = []
    defaulted_periods: list[str] = []
    ambiguity_flags: list[str] = []

    if not selected_company or (
        not selected_company.get("stock_abbr")
        and not selected_company.get("stock_code")
    ):
        missing_fields.append("missing_company")
    if not selected_metric:
        missing_fields.append("missing_metric")

    if bool(company.get("ambiguous")):
        ambiguity_flags.append("ambiguous_company")
    if bool(metric_result.get("ambiguous")):
        ambiguity_flags.append("ambiguous_metric")

    if intent == "single_value" and report_period is None:
        missing_fields.append("missing_report_period")
    if intent == "trend":
        if recent_years is not None:
            defaulted_periods.append(f"recent_years:{recent_years}")
        elif isinstance(previous.get("recent_years"), int) and allow_follow_up:
            recent_years = cast(int, previous["recent_years"])
            defaulted_periods.append(f"recent_years:{recent_years}")

    result: dict[str, object] = {
        "question": question,
        "normalized_question": normalized_question,
        "stock_code": (selected_company or {}).get("stock_code") or None,
        "stock_abbr": (selected_company or {}).get("stock_abbr") or None,
        "report_period": report_period,
        "report_year": report_year,
        "intent": intent,
        "metric_name": (selected_metric or {}).get("name") or None,
        "metric_column": (selected_metric or {}).get("column") or None,
        "table_name": (selected_metric or {}).get("table") or None,
        "recent_years": recent_years,
        "missing_fields": missing_fields,
        "defaulted_periods": defaulted_periods,
        "metric_candidates": metric_candidates,
        "company_candidates": company_candidates,
        "ambiguity_flags": ambiguity_flags,
        "carry_applied": carry_applied,
        "judge_needed": bool(ambiguity_flags),
        "resolver_confidence": _resolver_confidence(
            missing_fields=missing_fields,
            ambiguity_flags=ambiguity_flags,
            carry_applied=carry_applied,
        ),
    }
    return result
