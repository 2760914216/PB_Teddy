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
    parser = argparse.ArgumentParser(description="Check section scoping")
    parser.add_argument("--pdf-dir", default="test_set")
    args = parser.parse_args()

    failures = []
    for filename in sorted(os.listdir(args.pdf_dir)):
        pdf_path = os.path.join(args.pdf_dir, filename)
        parser_obj = PDFParser(pdf_path)
        extractor = FieldExtractor(parser_obj)
        try:
            pages = {
                key: [
                    page + 1
                    for page in extractor._section_pages(keyword, max_pages=max_pages)
                ]
                for key, (keyword, max_pages) in extractor._SECTION_KEYWORDS.items()
            }
            print(filename, pages)
            if filename.startswith("600080"):
                income_rows = extractor._get_rows("income", "合并利润表", max_pages=8)
                if any(
                    row["row_name"] in {"资本公积", "未分配利润"} for row in income_rows
                ):
                    failures.append(
                        f"pre-header balance rows leaked into income section for {filename}"
                    )
                if any(page <= 3 for page in pages["income"]):
                    failures.append(
                        f"income section fell into front matter for {filename}"
                    )
        finally:
            parser_obj.close()

    if failures:
        for failure in failures:
            print("FAIL", failure)
        sys.exit(1)


if __name__ == "__main__":
    main()
