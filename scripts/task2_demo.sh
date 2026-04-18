#!/usr/bin/env bash
set -euo pipefail

python3 scripts/task2_preflight.py --config config.yaml
python3 scripts/task2_smoke_batch.py --config config.yaml --input 示例数据/task2_sample.json
python3 scripts/task2_smoke_export.py --config config.yaml --input 示例数据/task2_sample.json
