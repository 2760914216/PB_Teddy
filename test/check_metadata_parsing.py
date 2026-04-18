# pyright: reportMissingImports=false
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from extraction_support import fixture_pdf_paths
from pdfExtractor.pdf_parser import PDFParser
from pdfExtractor.utils import parse_report_period


def main():
    parser = argparse.ArgumentParser(
        description="Check metadata parsing for fixture PDFs"
    )
    parser.add_argument("--pdf-dir", default="test_set")
    parser.add_argument("--simulate-mismatch", action="store_true")
    args = parser.parse_args()

    failures = []
    for pdf_path in fixture_pdf_paths(args.pdf_dir):
        parser_obj = PDFParser(str(pdf_path))
        try:
            stock_code, stock_abbr = parser_obj.get_stock_info()
            report_period, report_year = parser_obj.get_report_period()
            print(pdf_path.name, stock_code, stock_abbr, report_period, report_year)
            if not stock_code or not stock_abbr or not report_period:
                failures.append(f"missing metadata for {pdf_path.name}")

            if args.simulate_mismatch:
                text = "\n".join(
                    parser_obj.get_page_text(i)
                    for i in range(min(8, len(parser_obj._require_pdf().pages)))
                )
                fake_name = pdf_path.name.replace("2024", "2099", 1)
                fallback_period, _ = parse_report_period(text, fake_name)
                print("mismatch", pdf_path.name, "->", fallback_period)
                if fallback_period != report_period:
                    failures.append(f"mismatch fallback failed for {pdf_path.name}")
        finally:
            parser_obj.close()

    if failures:
        for failure in failures:
            print("FAIL", failure)
        sys.exit(1)


if __name__ == "__main__":
    main()
