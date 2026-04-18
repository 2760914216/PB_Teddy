# pyright: reportMissingImports=false
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pdfExtractor.pdf_parser import PDFParser
from pdfExtractor.field_extractor import FieldExtractor


def main():
    parser = argparse.ArgumentParser(description="Check core dependency reuse")
    parser.add_argument("--pdf-dir", default="test_set")
    args = parser.parse_args()

    failures = []
    for filename in sorted(os.listdir(args.pdf_dir)):
        parser_obj = PDFParser(os.path.join(args.pdf_dir, filename))
        extractor = FieldExtractor(parser_obj)
        try:
            core = extractor.extract_core_indicators() or {}
            cache_keys = set(extractor._statement_cache)
            print(
                filename,
                cache_keys,
                core.get("total_operating_revenue"),
                core.get("net_profit_10k_yuan"),
            )
            if not {"income", "balance", "cashflow", "core"}.issubset(cache_keys):
                failures.append(f"statement cache incomplete for {filename}")
            income = extractor._statement_cache.get("income") or {}
            if core.get("total_operating_revenue") != income.get(
                "total_operating_revenue"
            ):
                failures.append(f"core revenue not reused from income for {filename}")
        finally:
            parser_obj.close()

    if failures:
        for failure in failures:
            print("FAIL", failure)
        sys.exit(1)


if __name__ == "__main__":
    main()
