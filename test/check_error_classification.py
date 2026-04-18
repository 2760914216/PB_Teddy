# pyright: reportMissingImports=false
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pdfExtractor.db_handler import DataValidationError
from pdfExtractor.main import process_pdf


class StubDB:
    def begin(self):
        return None

    def rollback(self):
        return None

    def insert_income_sheet(self, data, *, commit=True):
        return None

    def insert_balance_sheet(self, data, *, commit=True):
        return None

    def insert_cash_flow_sheet(self, data, *, commit=True):
        return None

    def insert_core_indicators(self, data, *, commit=True):
        raise DataValidationError(
            "core_performance_indicators_sheet",
            "net_asset_per_share",
            99999999.0,
            "forced classification check",
        )


def main():
    parser = argparse.ArgumentParser(
        description="Check structured error classification"
    )
    parser.add_argument("--pdf-dir", default="test_set")
    args = parser.parse_args()

    error_log = []
    success = process_pdf(
        f"{args.pdf_dir}/600080_20240427_0WKP.pdf", StubDB(), error_log
    )
    print("success", success)
    print(json.dumps(error_log, ensure_ascii=False, indent=2))
    if success or not error_log:
        print("FAIL expected structured error output")
        sys.exit(1)
    entry = error_log[0]
    for key in ("failure_stage", "reason", "details"):
        if key not in entry:
            print("FAIL missing key", key)
            sys.exit(1)


if __name__ == "__main__":
    main()
