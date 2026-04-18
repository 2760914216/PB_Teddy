from __future__ import annotations

from typing import cast


def choose_chart_type(
    query_result: dict[str, object],
    requested_chart: str | None = None,
) -> str:
    if requested_chart and requested_chart not in {"none", ""}:
        return requested_chart

    rows = cast(list[object], query_result.get("rows") or [])
    columns = [
        str(column) for column in cast(list[object], query_result.get("columns") or [])
    ]
    if not isinstance(rows, list) or len(rows) <= 1:
        return "none"
    if "report_period" in columns:
        return "line"
    numeric_columns = [
        column
        for column in columns
        if column not in {"stock_abbr", "report_period", "report_year"}
    ]
    if len(rows) <= 8 and len(numeric_columns) == 1:
        return "bar"
    return "table"
