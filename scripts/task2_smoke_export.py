from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test Task2 export flow")
    parser.add_argument("--config", default="config.yaml", help="Task2 config path")
    parser.add_argument("--input", default="", help="Attachment4-equivalent JSON input")
    parser.add_argument("--use-llm", action="store_true", help="Enable Ollama planning")
    args = parser.parse_args()

    if not args.input:
        print("FAIL: missing Attachment4-equivalent sample input (--input)")
        return 1

    batch_module = importlib.import_module("src.task2.batch_adapter")
    exporter_module = importlib.import_module("src.task2.exporter")
    run_batch = getattr(batch_module, "run_batch")
    export_results = getattr(exporter_module, "export_results")

    records = run_batch(args.input, args.config, use_llm=args.use_llm)
    paths = export_results(records, args.config)
    dataframe = pd.read_excel(paths["xlsx_path"])
    print(json.dumps(paths, ensure_ascii=False))
    print(dataframe.columns.tolist())
    print("PASS: export smoke succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
