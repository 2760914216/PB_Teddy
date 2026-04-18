from __future__ import annotations

import importlib
import json
from pathlib import Path

import pandas as pd

from .config import Task2Config, load_task2_config


def export_results(
    records: list[dict[str, object]],
    config: str | Task2Config = "config.yaml",
) -> dict[str, str]:
    loaded_config = load_task2_config(config) if isinstance(config, str) else config
    submission_module = importlib.import_module("src.task2.submission")
    conversation_to_attachment7 = getattr(
        submission_module, "conversation_to_attachment7"
    )
    conversation_to_export_row = getattr(
        submission_module, "conversation_to_export_row"
    )

    loaded_config.ensure_output_dirs()
    json_path = loaded_config.result_dir_path / "task2_answers.json"
    xlsx_path = loaded_config.result_dir_path / "result_2.xlsx"

    attachment7_payload = [
        {
            "编号": str(record.get("question_id") or ""),
            "回答": conversation_to_attachment7(record),
        }
        for record in records
    ]
    json_path.write_text(
        json.dumps(attachment7_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    rows = [conversation_to_export_row(record) for record in records]
    dataframe = pd.DataFrame(
        rows, columns=["编号", "问题", "SQL查询语句", "图形格式", "回答"]
    )
    dataframe.to_excel(xlsx_path, index=False, engine="openpyxl")

    return {"json_path": str(json_path), "xlsx_path": str(xlsx_path)}
