# pyright: reportMissingImports=false
import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TEST_DIR = ROOT / "test"
if str(TEST_DIR) not in sys.path:
    sys.path.insert(0, str(TEST_DIR))

from extraction_support import (
    DEFAULT_GOLDEN_PATH,
    extract_single_pdf,
    fixture_pdf_paths,
    load_golden,
    sanitize_filename,
)


def main():
    parser = argparse.ArgumentParser(
        description="Export four-PDF extraction diagnostics"
    )
    parser.add_argument("--pdf-dir", default="test_set")
    parser.add_argument("--out-dir", default=".sisyphus/evidence/diagnostics")
    parser.add_argument("--golden", default=str(DEFAULT_GOLDEN_PATH))
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    golden = load_golden(args.golden)
    summary: dict[str, Any] = {
        "pdf_count": 0,
        "known_failures": golden.get("failure_assertions", {}),
        "files": [],
    }

    for pdf_path in fixture_pdf_paths(args.pdf_dir):
        payload = extract_single_pdf(pdf_path)
        target = out_dir / f"{sanitize_filename(pdf_path.stem)}.json"
        with open(target, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        summary["pdf_count"] += 1
        summary["files"].append(target.name)
        print(f"diagnostic {pdf_path.name} -> {target}")

    summary_path = out_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
    print(f"summary -> {summary_path}")


if __name__ == "__main__":
    main()
