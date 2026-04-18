from __future__ import annotations

import importlib

from .config import Task2Config, load_task2_config


def execute_sql_plan(
    plan: dict[str, object],
    config: str | Task2Config = "config.yaml",
) -> dict[str, object]:
    loaded_config = load_task2_config(config) if isinstance(config, str) else config
    sql = str(plan.get("sql") or "")
    if not sql:
        return {
            "status": "blocked",
            "sql": "",
            "columns": [],
            "rows": [],
            "row_count": 0,
            "message": "当前计划没有可执行 SQL。",
        }

    guardrails = importlib.import_module("src.task2.sql_guardrails")
    executor_module = importlib.import_module("src.task2.db_executor")
    normalizer_module = importlib.import_module("src.task2.result_normalizer")

    validate_sql = getattr(guardrails, "validate_sql")
    executor_class = getattr(executor_module, "ReadOnlyDBExecutor")
    normalize_query_result = getattr(normalizer_module, "normalize_query_result")

    validated = validate_sql(sql, default_limit=loaded_config.task2.max_rows)
    executor = executor_class(loaded_config)
    rows, metadata = executor.execute_with_metadata(validated)
    return normalize_query_result(validated.normalized_sql, rows, metadata.columns)
