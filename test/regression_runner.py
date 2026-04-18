# pyright: reportMissingImports=false
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from extraction_support import (
    DEFAULT_GOLDEN_PATH,
    FIXTURE_FILES,
    TABLES,
    coerce_float,
    keyed_rows,
    load_csv_rows,
    load_golden,
    run_pipeline,
)


def main():
    parser = argparse.ArgumentParser(description="Run four-PDF regression checks")
    parser.add_argument("--pdf-dir", default="test_set")
    parser.add_argument("--output-dir", default="test_ex_db_result")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--golden", default=str(DEFAULT_GOLDEN_PATH))
    args = parser.parse_args()

    golden = load_golden(args.golden)
    summary = run_pipeline(
        args.pdf_dir,
        args.output_dir,
        config_path=args.config,
        golden_path=args.golden,
        cleanup=True,
    )

    failures: list[str] = []
    passes: list[str] = []

    if summary["success_count"] == summary["total"] == len(FIXTURE_FILES):
        passes.append(
            f"pipeline processed {summary['success_count']}/{summary['total']} fixtures"
        )
    else:
        failures.append(
            f"pipeline processed {summary['success_count']}/{summary['total']} fixtures"
        )

    table_rows = {table: load_csv_rows(args.output_dir, table) for table in TABLES}
    for table, rows in table_rows.items():
        if len(rows) == len(FIXTURE_FILES):
            passes.append(f"{table} row count = {len(rows)}")
        else:
            failures.append(
                f"{table} row count = {len(rows)} (expected {len(FIXTURE_FILES)})"
            )

    keyed = {table: keyed_rows(rows) for table, rows in table_rows.items()}
    for fixture in golden["fixtures"]:
        key = (fixture["stock_code"], fixture["report_period"])
        for table, expected_fields in fixture["statements"].items():
            row = keyed[table].get(key)
            if row is None:
                failures.append(f"missing row {table} {key}")
                continue
            for field, rule in expected_fields.items():
                actual = coerce_float(row.get(field))
                expected = coerce_float(rule.get("expected"))
                tolerance = float(rule.get("tolerance", 0))
                if actual is None and expected is None:
                    passes.append(f"{table} {key} {field} is null as expected")
                    continue
                if actual is None or expected is None:
                    failures.append(
                        f"{table} {key} {field} expected {expected}, got {actual}"
                    )
                    continue
                if abs(actual - expected) <= tolerance:
                    passes.append(f"{table} {key} {field}={actual}")
                else:
                    failures.append(
                        f"{table} {key} {field}={actual} expected {expected}±{tolerance}"
                    )

    banned_value = golden["failure_assertions"]["blocked_dirty_value"]
    for table, rows in table_rows.items():
        for row in rows:
            key = (row["stock_code"], row["report_period"])
            for column, value in row.items():
                if value == banned_value:
                    failures.append(
                        f"dirty marker {banned_value} found in {table} {key} {column}"
                    )

    errors_log_text = (
        Path(summary["error_log_path"]).read_text(encoding="utf-8").strip()
    )
    if golden["failure_assertions"].get("require_no_errors_log", True):
        if errors_log_text == "No errors":
            passes.append("errors.log clean")
        else:
            failures.append(f"errors.log not clean: {errors_log_text}")

    print("Regression summary")
    for item in passes:
        print(f"PASS: {item}")
    for item in failures:
        print(f"FAIL: {item}")

    sys.exit(0 if not failures else 1)


if __name__ == "__main__":
    main()
