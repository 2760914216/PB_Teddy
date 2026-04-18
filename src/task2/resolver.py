from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path

import pymysql

from .config import Task2Config, load_task2_config

METRIC_CATALOG: tuple[dict[str, str], ...] = (
    {"name": "利润总额", "column": "total_profit", "table": "income_sheet"},
    {"name": "净利润", "column": "net_profit", "table": "income_sheet"},
    {
        "name": "营业总收入",
        "column": "total_operating_revenue",
        "table": "income_sheet",
    },
    {"name": "营业收入", "column": "total_operating_revenue", "table": "income_sheet"},
    {"name": "营业利润", "column": "operating_profit", "table": "income_sheet"},
    {"name": "每股收益", "column": "eps", "table": "core_performance_indicators_sheet"},
    {
        "name": "基本每股收益",
        "column": "eps",
        "table": "core_performance_indicators_sheet",
    },
    {
        "name": "净资产收益率",
        "column": "roe",
        "table": "core_performance_indicators_sheet",
    },
    {"name": "ROE", "column": "roe", "table": "core_performance_indicators_sheet"},
    {"name": "资产总计", "column": "asset_total_assets", "table": "balance_sheet"},
    {"name": "总资产", "column": "asset_total_assets", "table": "balance_sheet"},
    {
        "name": "负债合计",
        "column": "liability_total_liabilities",
        "table": "balance_sheet",
    },
    {
        "name": "总负债",
        "column": "liability_total_liabilities",
        "table": "balance_sheet",
    },
    {"name": "资产负债率", "column": "asset_liability_ratio", "table": "balance_sheet"},
    {
        "name": "现金及现金等价物净增加额",
        "column": "net_cash_flow",
        "table": "cash_flow_sheet",
    },
    {"name": "现金净增加额", "column": "net_cash_flow", "table": "cash_flow_sheet"},
)

TREND_KEYWORDS = ("趋势", "变化", "走势", "波动", "变动")


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


def _infer_metric(question: str) -> dict[str, str] | None:
    ranked = sorted(METRIC_CATALOG, key=lambda item: len(item["name"]), reverse=True)
    for metric in ranked:
        if metric["name"] in question:
            return metric
    return None


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


def _resolve_company(question: str, config: Task2Config) -> dict[str, str]:
    catalog = _load_company_catalog(str(config.config_path))
    for stock_code, stock_abbr in catalog:
        if stock_abbr and stock_abbr in question:
            return {"stock_code": stock_code, "stock_abbr": stock_abbr}

    code_match = re.search(r"\b(\d{6})\b", question)
    if code_match:
        code = code_match.group(1)
        for stock_code, stock_abbr in catalog:
            if stock_code == code:
                return {"stock_code": stock_code, "stock_abbr": stock_abbr}
        return {"stock_code": code, "stock_abbr": ""}

    return {"stock_code": "", "stock_abbr": ""}


def resolve_question_context(
    question: str,
    config: str | Task2Config = "config.yaml",
    previous_context: dict[str, object] | None = None,
) -> dict[str, object]:
    loaded_config = load_task2_config(config) if isinstance(config, str) else config
    normalized_question = _normalize_question(question)
    previous = previous_context or {}

    company = _resolve_company(normalized_question, loaded_config)
    previous_stock_code = previous.get("stock_code")
    previous_stock_abbr = previous.get("stock_abbr")
    if not company["stock_code"] and isinstance(previous_stock_code, str):
        company["stock_code"] = previous_stock_code
    if not company["stock_abbr"] and isinstance(previous_stock_abbr, str):
        company["stock_abbr"] = previous_stock_abbr

    report_period, report_year = _parse_explicit_period(normalized_question)
    if (
        report_period is None
        and isinstance(previous.get("report_period"), str)
        and not re.search(r"20\d{2}", normalized_question)
    ):
        report_period = previous["report_period"]
    if (
        report_year is None
        and isinstance(previous.get("report_year"), int)
        and report_period == previous.get("report_period")
    ):
        report_year = previous["report_year"]

    intent = _infer_intent(normalized_question)
    metric = _infer_metric(normalized_question)
    if (
        metric is None
        and isinstance(previous.get("metric_name"), str)
        and isinstance(previous.get("metric_column"), str)
    ):
        metric = {
            "name": previous["metric_name"],
            "column": previous["metric_column"],
            "table": str(previous.get("table_name", "")),
        }

    recent_years = _parse_recent_years(
        normalized_question, loaded_config.task2.default_recent_years
    )
    missing_fields: list[str] = []
    defaulted_periods: list[str] = []

    if not company["stock_abbr"] and not company["stock_code"]:
        missing_fields.append("missing_company")
    if metric is None:
        missing_fields.append("missing_metric")

    if intent == "single_value" and report_period is None:
        missing_fields.append("missing_report_period")
    if intent == "trend" and recent_years is not None:
        defaulted_periods.append(f"recent_years:{recent_years}")

    result: dict[str, object] = {
        "question": question,
        "normalized_question": normalized_question,
        "stock_code": company["stock_code"] or None,
        "stock_abbr": company["stock_abbr"] or None,
        "report_period": report_period,
        "report_year": report_year,
        "intent": intent,
        "metric_name": metric["name"] if metric else None,
        "metric_column": metric["column"] if metric else None,
        "table_name": metric["table"] if metric else None,
        "recent_years": recent_years,
        "missing_fields": missing_fields,
        "defaulted_periods": defaulted_periods,
    }
    return result
