from __future__ import annotations


PERIOD_RANK = {"Q1": 1, "HY": 2, "Q3": 3, "FY": 4}


def _period_sort_key(row: dict[str, object]) -> tuple[int, int]:
    report_year = row.get("report_year")
    report_period = str(row.get("report_period") or "")
    suffix = (
        report_period[-2:]
        if report_period.endswith("FY") or report_period.endswith("HY")
        else report_period[-2:]
    )
    rank = PERIOD_RANK.get(suffix, 99)
    return (int(report_year) if isinstance(report_year, int) else 0, rank)


def normalize_query_result(
    sql: str,
    rows: list[dict[str, object]],
    columns: tuple[str, ...],
) -> dict[str, object]:
    cleaned_rows = [dict(row) for row in rows]
    if "report_year" in columns or "report_period" in columns:
        cleaned_rows.sort(key=_period_sort_key)

    if not cleaned_rows:
        return {
            "status": "no_data",
            "sql": sql,
            "columns": list(columns),
            "rows": [],
            "row_count": 0,
            "message": "未查询到符合条件的数据。",
        }

    return {
        "status": "ok",
        "sql": sql,
        "columns": list(columns),
        "rows": cleaned_rows,
        "row_count": len(cleaned_rows),
        "message": None,
    }
