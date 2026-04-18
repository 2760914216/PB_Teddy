from __future__ import annotations

PROBE_CASES: tuple[dict[str, object], ...] = (
    {
        "question_id": "B1001",
        "question": "金花股份利润总额是多少",
        "expected": {
            "needs_clarification": True,
            "table_name": "income_sheet",
            "metric_column": "total_profit",
        },
    },
    {
        "question_id": "B1002",
        "question": "金花股份近几年的利润总额变化趋势是什么样的",
        "expected": {
            "needs_clarification": False,
            "table_name": "income_sheet",
            "metric_column": "total_profit",
            "chart_recommendation": "line",
        },
    },
)
