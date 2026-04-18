# pyright: reportMissingImports=false
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pdfExtractor.pdf_parser import PDFParser
from pdfExtractor.field_extractor import FieldExtractor


def main():
    failures = []
    for name in ["600080_20240427_0WKP.pdf", "600080_20240817_5X5X.pdf"]:
        parser = PDFParser(os.path.join("test_set", name))
        extractor = FieldExtractor(parser)
        try:
            rows = extractor._get_rows("income", "合并利润表", max_pages=8)
            match = extractor._match_field_from_rows(
                rows,
                FieldExtractor._ALIASES["income"]["total_operating_revenue"],
            )
            print(name, match and match["row"]["row_name"], match and match["current"])
            if not match or match["current"] in (0.0, 0.01, None):
                failures.append(f"revenue collision unresolved for {name}")
            if match and "营业外收入" in match["row"]["row_name"]:
                failures.append(f"wrong row won revenue match for {name}")
        finally:
            parser.close()

    if failures:
        for failure in failures:
            print("FAIL", failure)
        sys.exit(1)


if __name__ == "__main__":
    main()
