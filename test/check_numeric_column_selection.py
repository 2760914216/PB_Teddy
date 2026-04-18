# pyright: reportMissingImports=false
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from extraction_support import extract_single_pdf, fixture_pdf_paths


def main():
    parser = argparse.ArgumentParser(description="Check numeric column selection")
    parser.add_argument("--pdf-dir", default="test_set")
    args = parser.parse_args()

    failures = []
    for pdf_path in fixture_pdf_paths(args.pdf_dir):
        payload = extract_single_pdf(pdf_path)
        income = payload["statements"]["income_sheet"] or {}
        core = payload["statements"]["core_performance_indicators_sheet"] or {}
        print(
            pdf_path.name,
            income.get("total_operating_revenue"),
            core.get("net_asset_per_share"),
        )
        if income.get("total_operating_revenue") in (0.0, 0.01, None):
            failures.append(f"bad revenue value for {pdf_path.name}")
        if pdf_path.name.startswith("600080") and core.get("net_asset_per_share") in (
            None,
            0.0,
            0.01,
        ):
            failures.append(f"bad net_asset_per_share for {pdf_path.name}")

    if failures:
        for failure in failures:
            print("FAIL", failure)
        sys.exit(1)


if __name__ == "__main__":
    main()
