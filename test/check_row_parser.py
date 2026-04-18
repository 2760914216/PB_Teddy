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
    parser = argparse.ArgumentParser(description="Check row parser behavior")
    parser.add_argument("--pdf-dir", default="test_set")
    parser.add_argument("--focus", default="600080")
    args = parser.parse_args()

    failures = []
    for path in sorted(os.listdir(args.pdf_dir)):
        if args.focus not in path:
            continue
        pdf_path = os.path.join(args.pdf_dir, path)
        parser_obj = PDFParser(pdf_path)
        extractor = FieldExtractor(parser_obj)
        try:
            rows = extractor.inspect_section_rows("合并利润表", max_pages=8)
            accepted = [row for row in rows if row.get("accepted")]
            rejected = [row for row in rows if not row.get("accepted")]
            print(path, "accepted", len(accepted), "rejected", len(rejected))
            revenue_rows = [
                row
                for row in accepted
                if row.get("row_name")
                in {"其中:营业收入", "其中：营业收入", "一、营业总收入"}
            ]
            for row in revenue_rows:
                print(row["row_name"], row.get("note_ref"), row.get("numeric_cells"))
                if row.get("note_ref") and row.get("numeric_cells", [None])[0] in {
                    row.get("note_ref"),
                    "七、61",
                    "十九、4",
                }:
                    failures.append(f"note ref leaked into numeric cells for {path}")
            if not rejected:
                failures.append(f"no rejected noise rows found for {path}")
        finally:
            parser_obj.close()

    if failures:
        for failure in failures:
            print("FAIL", failure)
        sys.exit(1)


if __name__ == "__main__":
    main()
