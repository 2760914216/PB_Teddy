from __future__ import annotations

import importlib
import pymysql

from .config import Task2Config, load_task2_config


def _latest_report_year(
    config: Task2Config, table_name: str, stock_abbr: str | None
) -> int | None:
    if not stock_abbr:
        return None
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
                    f"SELECT MAX(report_year) AS latest_year FROM {table_name} WHERE stock_abbr = %s",
                    (stock_abbr,),
                )
                row = cursor.fetchone() or {}
        finally:
            connection.close()
    except Exception:
        return None
    latest_year = row.get("latest_year")
    if isinstance(latest_year, int):
        return latest_year
    if isinstance(latest_year, str) and latest_year.isdigit():
        return int(latest_year)
    return None


def _available_report_periods(
    config: Task2Config, table_name: str, stock_abbr: str | None
) -> list[str]:
    if not stock_abbr:
        return []
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
                    f"SELECT DISTINCT report_period, report_year FROM {table_name} WHERE stock_abbr = %s ORDER BY report_year, report_period",
                    (stock_abbr,),
                )
                rows = cursor.fetchall()
        finally:
            connection.close()
    except Exception:
        return []
    return [
        str(row.get("report_period") or "") for row in rows if row.get("report_period")
    ]


def _pick_trend_periods(
    available_periods: list[str], *, start_year: int, end_year: int
) -> list[str]:
    rank = {"Q1": 1, "HY": 2, "Q3": 3, "FY": 4}
    by_year: dict[int, list[str]] = {}
    for period in available_periods:
        if len(period) < 6 or not period[:4].isdigit():
            continue
        year = int(period[:4])
        by_year.setdefault(year, []).append(period)

    selected: list[str] = []
    for year in range(start_year, end_year + 1):
        options = by_year.get(year, [])
        if not options:
            continue
        preferred = sorted(options, key=lambda value: rank.get(value[-2:], 0))[-1]
        if year < end_year:
            annual = [item for item in options if item.endswith("FY")]
            if annual:
                preferred = annual[0]
        selected.append(preferred)
    return selected


def _heuristic_plan(
    resolved_context: dict[str, object], config: Task2Config
) -> dict[str, object]:
    intent = str(resolved_context.get("intent") or "single_value")
    stock_abbr = str(resolved_context.get("stock_abbr") or "")
    report_period = resolved_context.get("report_period")
    report_year = resolved_context.get("report_year")
    metric_name = str(resolved_context.get("metric_name") or "")
    metric_column = str(resolved_context.get("metric_column") or "")
    table_name = str(resolved_context.get("table_name") or "")
    question = str(resolved_context.get("question") or "")
    recent_years = resolved_context.get("recent_years")

    if intent == "trend":
        latest_year = _latest_report_year(config, table_name, stock_abbr)
        target_year = report_year if isinstance(report_year, int) else latest_year
        if not isinstance(recent_years, int):
            recent_years = config.task2.default_recent_years
        if not isinstance(target_year, int):
            target_year = 2025
        start_year = max(2000, target_year - recent_years + 1)
        available_periods = _available_report_periods(config, table_name, stock_abbr)
        selected_periods = _pick_trend_periods(
            available_periods, start_year=start_year, end_year=target_year
        )
        if selected_periods:
            quoted_periods = ", ".join(f"'{period}'" for period in selected_periods)
            period_filter = f"AND report_period IN ({quoted_periods}) "
        else:
            period_filter = (
                f"AND report_year >= {start_year} AND report_year <= {target_year} "
            )
        sql = (
            f"SELECT stock_abbr, report_year, report_period, {metric_column} "
            f"FROM {table_name} "
            f"WHERE stock_abbr = '{stock_abbr}' {period_filter}"
            f"ORDER BY report_year, report_period"
        )
        return {
            "intent": "trend",
            "needs_clarification": False,
            "clarification_question": None,
            "sql": sql,
            "table_name": table_name,
            "metric_name": metric_name,
            "metric_column": metric_column,
            "chart_recommendation": "line",
            "analysis_focus": [f"关注 {metric_name} 的年度变化和拐点"],
            "planner_source": "heuristic",
            "question": question,
            "selected_periods": selected_periods,
        }

    sql = (
        f"SELECT stock_abbr, report_period, {metric_column} FROM {table_name} "
        f"WHERE stock_abbr = '{stock_abbr}' AND report_period = '{report_period}'"
    )
    return {
        "intent": "single_value",
        "needs_clarification": False,
        "clarification_question": None,
        "sql": sql,
        "table_name": table_name,
        "metric_name": metric_name,
        "metric_column": metric_column,
        "chart_recommendation": "none",
        "analysis_focus": [f"直接回答 {report_period} 的 {metric_name}"],
        "planner_source": "heuristic",
        "question": question,
    }


def _llm_plan(
    question: str, resolved_context: dict[str, object], config: Task2Config
) -> dict[str, object] | None:
    prompts_module = importlib.import_module("src.task2.prompts_nl2sql")
    llm_module = importlib.import_module("src.task2.llm_client")
    build_prompt = getattr(prompts_module, "build_nl2sql_prompt")
    llm_client_class = getattr(llm_module, "Task2LLMClient")

    client = llm_client_class(config)
    system_prompt, user_prompt = build_prompt(
        question, resolved_context, config.task2.max_rows
    )
    try:
        llm_output = client.chat_json(system_prompt, user_prompt)
    except Exception:
        return None
    if not isinstance(llm_output.get("sql"), str):
        return None
    return {
        "intent": str(
            llm_output.get("intent") or resolved_context.get("intent") or "single_value"
        ),
        "needs_clarification": bool(llm_output.get("needs_clarification", False)),
        "clarification_question": llm_output.get("clarification_question"),
        "sql": llm_output.get("sql"),
        "table_name": resolved_context.get("table_name"),
        "metric_name": resolved_context.get("metric_name"),
        "metric_column": resolved_context.get("metric_column"),
        "chart_recommendation": str(llm_output.get("chart_recommendation") or "none"),
        "analysis_focus": llm_output.get("analysis_focus") or [],
        "planner_source": "llm",
        "question": question,
    }


def build_sql_plan(
    question: str,
    config: str | Task2Config = "config.yaml",
    previous_context: dict[str, object] | None = None,
    *,
    use_llm: bool = True,
) -> dict[str, object]:
    loaded_config = load_task2_config(config) if isinstance(config, str) else config
    resolver_module = importlib.import_module("src.task2.resolver")
    clarification_module = importlib.import_module("src.task2.clarification")
    intent_judge_module = importlib.import_module("src.task2.intent_judge")
    resolve_question_context = getattr(resolver_module, "resolve_question_context")
    precheck_required_fields = getattr(clarification_module, "precheck_required_fields")
    finalize_clarification = getattr(clarification_module, "finalize_clarification")
    run_intent_judge = getattr(intent_judge_module, "run_intent_judge")

    resolved_context = resolve_question_context(
        question, loaded_config, previous_context
    )
    precheck = precheck_required_fields(resolved_context)
    if bool(precheck.get("needs_clarification")):
        return {
            "intent": str(resolved_context.get("intent") or "single_value"),
            "needs_clarification": True,
            "clarification_question": precheck.get("question"),
            "sql": None,
            "table_name": resolved_context.get("table_name"),
            "metric_name": resolved_context.get("metric_name"),
            "metric_column": resolved_context.get("metric_column"),
            "chart_recommendation": "none",
            "analysis_focus": [],
            "planner_source": "clarification",
            "resolved_context": precheck.get("final_context") or resolved_context,
        }

    judge_result = run_intent_judge(
        question,
        resolved_context,
        loaded_config,
        use_llm=use_llm,
    )
    clarification = finalize_clarification(resolved_context, judge_result)
    final_context = dict(clarification.get("final_context") or resolved_context)
    if bool(clarification.get("needs_clarification")):
        planner_source = (
            "judge"
            if str(judge_result.get("status") or "") == "clarify"
            and str(judge_result.get("source") or "") == "judge"
            else "clarification"
        )
        return {
            "intent": str(final_context.get("intent") or "single_value"),
            "needs_clarification": True,
            "clarification_question": clarification.get("question"),
            "sql": None,
            "table_name": final_context.get("table_name"),
            "metric_name": final_context.get("metric_name"),
            "metric_column": final_context.get("metric_column"),
            "chart_recommendation": "none",
            "analysis_focus": [],
            "planner_source": planner_source,
            "resolved_context": final_context,
        }

    heuristic_plan = _heuristic_plan(final_context, loaded_config)
    if use_llm:
        llm_plan = _llm_plan(question, final_context, loaded_config)
        if llm_plan is not None and not bool(llm_plan.get("needs_clarification")):
            heuristic_plan.update(llm_plan)
    heuristic_plan["resolved_context"] = final_context
    heuristic_plan["judge_result"] = judge_result
    return heuristic_plan
