from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Task2 preflight checks")
    parser.add_argument("--config", default="config.yaml", help="Task2 config path")
    args = parser.parse_args()

    preflight_module = importlib.import_module("src.task2.preflight")
    run_preflight = getattr(preflight_module, "run_preflight")
    report = run_preflight(args.config)
    checks = report.get("checks") if isinstance(report, dict) else {}
    if isinstance(checks, dict):
        for item in checks.values():
            if isinstance(item, dict):
                print(item.get("message"))
    print("VERDICT:", "PASS" if bool(report.get("ok")) else "FAIL")
    return 0 if bool(report.get("ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
