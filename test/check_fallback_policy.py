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
        description="Check controlled fallback diagnostics"
    )
    parser.add_argument("--pdf-dir", default="test_set")
    args = parser.parse_args()

    failures = []
    for pdf_path in fixture_pdf_paths(args.pdf_dir):
        payload = extract_single_pdf(pdf_path)
        fallback_entries = [
            entry
            for entry in payload["diagnostics"]
            if entry.get("reason") == "controlled_fallback"
        ]
        print(pdf_path.name, fallback_entries or "no-fallback")
        for entry in fallback_entries:
            for key in ("field", "page", "row_name", "score"):
                if key not in entry:
                    failures.append(
                        f"missing fallback detail {key} for {pdf_path.name}"
                    )

    if failures:
        for failure in failures:
            print("FAIL", failure)
        sys.exit(1)


if __name__ == "__main__":
    main()
