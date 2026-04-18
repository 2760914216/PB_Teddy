from __future__ import annotations

import importlib
import json
from pathlib import Path

from .config import Task2Config, load_task2_config


def _load_batch_input(input_path: Path) -> list[dict[str, object]]:
    if not input_path.exists():
        raise FileNotFoundError(f"缺少表1等价样例输入: {input_path}")
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise ValueError("batch 输入必须是对象数组")
    return [item for item in payload if isinstance(item, dict)]


def run_batch(
    input_path: str,
    config: str | Task2Config = "config.yaml",
    *,
    use_llm: bool = True,
) -> list[dict[str, object]]:
    loaded_config = load_task2_config(config) if isinstance(config, str) else config
    runtime_module = importlib.import_module("src.task2.runtime")
    run_conversation = getattr(runtime_module, "run_conversation")

    records: list[dict[str, object]] = []
    for item in _load_batch_input(Path(input_path)):
        question_id = str(item.get("编号") or item.get("question_id") or "")
        turns_raw = item.get("问题") or item.get("turns") or []
        if not question_id or not isinstance(turns_raw, list) or not turns_raw:
            raise ValueError("每条 batch 记录都必须包含 编号 和 问题数组")
        turns = [
            str(turn.get("Q") or "") for turn in turns_raw if isinstance(turn, dict)
        ]
        if not all(turns):
            raise ValueError(f"题号 {question_id} 存在空问题")
        records.append(
            run_conversation(question_id, turns, config=loaded_config, use_llm=use_llm)
        )
    return records
