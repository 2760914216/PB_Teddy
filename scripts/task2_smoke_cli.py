from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test Task2 CLI")
    parser.add_argument("--config", default="config.yaml", help="Task2 config path")
    args = parser.parse_args()

    cli = subprocess.run(
        [sys.executable, "-m", "src.task2.cli", "--config", args.config, "--no-llm"],
        cwd=ROOT,
        input="help\nquit\n",
        text=True,
        capture_output=True,
    )
    print(cli.stdout, end="")
    print(cli.stderr, end="")
    if cli.returncode == 0:
        print("PASS: cli smoke succeeded")
        return 0
    print("FAIL: cli smoke failed")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
