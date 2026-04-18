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
    parser = argparse.ArgumentParser(description="Check Task2 intent judge behavior")
    parser.add_argument("--config", default="config.yaml", help="Task2 config path")
    args = parser.parse_args()

    judge_module = importlib.import_module("src.task2.intent_judge")
    run_intent_judge = getattr(judge_module, "run_intent_judge")

    context = {
        "question": "金花股份利润是多少",
        "judge_needed": True,
        "metric_candidates": [
            {"name": "净利润", "column": "net_profit", "table": "income_sheet"},
            {"name": "利润总额", "column": "total_profit", "table": "income_sheet"},
            {"name": "营业利润", "column": "operating_profit", "table": "income_sheet"},
        ],
        "company_candidates": [{"stock_code": "600080", "stock_abbr": "金花股份"}],
    }

    valid_transport = lambda payload: {
        "message": {
            "content": '{"status":"resolved","confidence":0.91,"clarification_question":null,"reason":"按候选裁决","slot_updates":{"metric_name":"净利润","metric_column":"net_profit","table_name":"income_sheet"}}'
        }
    }
    valid_result = run_intent_judge(
        "金花股份利润是多少",
        context,
        args.config,
        transport=valid_transport,
    )
    print("[valid_result]", valid_result)
    _assert(
        valid_result.get("status") == "resolved", "valid judge output should resolve"
    )
    _assert(
        dict(valid_result.get("slot_updates") or {}).get("metric_column")
        == "net_profit",
        "valid judge output should keep candidate-backed metric",
    )

    low_confidence_transport = lambda payload: {
        "message": {
            "content": '{"status":"resolved","confidence":0.51,"clarification_question":null,"reason":"置信度不足","slot_updates":{"metric_name":"净利润","metric_column":"net_profit","table_name":"income_sheet"}}'
        }
    }
    low_confidence_result = run_intent_judge(
        "金花股份利润是多少",
        context,
        args.config,
        transport=low_confidence_transport,
    )
    print("[low_confidence_result]", low_confidence_result)
    _assert(
        low_confidence_result.get("status") == "abstain",
        "low confidence should abstain",
    )
    _assert(
        low_confidence_result.get("source") == "judge_low_confidence",
        "low confidence should use dedicated fallback source",
    )

    invalid_transport = lambda payload: {"message": {"content": "not-json"}}
    invalid_result = run_intent_judge(
        "金花股份利润是多少",
        context,
        args.config,
        transport=invalid_transport,
    )
    print("[invalid_result]", invalid_result)
    _assert(
        invalid_result.get("status") == "abstain",
        "invalid judge payload should abstain",
    )
    _assert(
        invalid_result.get("source") == "judge_fallback",
        "invalid judge payload should use fallback source",
    )

    print("PASS: judge checks succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
