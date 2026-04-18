# pyright: reportMissingImports=false
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from extraction_support import extract_single_pdf, fixture_pdf_paths


def main():
    parser = argparse.ArgumentParser(
        description="Check statement consistency for core reuse"
    )
    parser.add_argument("--pdf-dir", default="test_set")
    parser.add_argument("--focus", default="")
    args = parser.parse_args()

    failures = []
    for pdf_path in fixture_pdf_paths(args.pdf_dir):
        if args.focus and args.focus not in pdf_path.name:
            continue
        payload = extract_single_pdf(pdf_path)
        income = payload["statements"]["income_sheet"] or {}
        core = payload["statements"]["core_performance_indicators_sheet"] or {}
        print(
            pdf_path.name,
            income.get("total_operating_revenue"),
            core.get("total_operating_revenue"),
        )
        if core.get("total_operating_revenue") != income.get("total_operating_revenue"):
            failures.append(f"core/income revenue mismatch for {pdf_path.name}")
        if core.get("net_profit_10k_yuan") != income.get("net_profit"):
            failures.append(f"core/income net profit mismatch for {pdf_path.name}")

    if failures:
        for failure in failures:
            print("FAIL", failure)
        sys.exit(1)


if __name__ == "__main__":
    main()
