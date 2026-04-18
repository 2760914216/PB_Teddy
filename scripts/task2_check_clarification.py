from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Task2 clarification behavior")
    parser.add_argument("--config", default="config.yaml", help="Task2 config path")
    args = parser.parse_args()

    nl2sql_module = importlib.import_module("src.task2.nl2sql")
    build_sql_plan = getattr(nl2sql_module, "build_sql_plan")

    alias_plan = build_sql_plan(
        "金花股份2024年年报归母净利润是多少",
        args.config,
        use_llm=False,
    )
    print("[alias_plan]", alias_plan)
    _assert(
        not bool(alias_plan.get("needs_clarification")),
        "alias case should plan directly",
    )
    _assert(
        alias_plan.get("metric_column") == "net_profit",
        "alias should map to net_profit",
    )

    ambiguity_plan = build_sql_plan("金花股份利润是多少", args.config, use_llm=False)
    print("[ambiguity_plan]", ambiguity_plan)
    _assert(
        bool(ambiguity_plan.get("needs_clarification")),
        "ambiguous metric should clarify",
    )
    clarification_question = str(ambiguity_plan.get("clarification_question") or "")
    _assert(
        "净利润" in clarification_question,
        "clarification should mention candidate metrics",
    )
    _assert(
        "利润总额" in clarification_question,
        "clarification should mention total_profit candidate",
    )

    first_turn = build_sql_plan("金花股份利润总额是多少", args.config, use_llm=False)
    follow_up_plan = build_sql_plan(
        "2025年第三季度的",
        args.config,
        first_turn.get("resolved_context"),
        use_llm=False,
    )
    print("[follow_up_plan]", follow_up_plan)
    _assert(
        not bool(follow_up_plan.get("needs_clarification")),
        "follow-up should fill pending slots",
    )
    resolved_context = dict(follow_up_plan.get("resolved_context") or {})
    _assert(
        resolved_context.get("report_period") == "2025Q3",
        "follow-up should carry metric/company and resolve period",
    )
    _assert(
        resolved_context.get("metric_column") == "total_profit",
        "follow-up should preserve prior metric",
    )

    print("PASS: clarification checks succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
