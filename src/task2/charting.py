from __future__ import annotations

import importlib
from pathlib import Path
from typing import cast

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

from .config import Task2Config, load_task2_config


def _find_font_name(config: Task2Config) -> str | None:
    available = {item.name for item in font_manager.fontManager.ttflist}
    for candidate in config.task2.chart_font_candidates:
        if candidate in available:
            return candidate
    return None


def _chart_path(config: Task2Config, question_id: str, index: int) -> tuple[Path, str]:
    submission_module = importlib.import_module("src.task2.submission")
    normalize_question_id = getattr(submission_module, "normalize_question_id")
    config.ensure_output_dirs()
    normalized_question_id = normalize_question_id(question_id)
    filename = f"{normalized_question_id}_{index}.jpg"
    absolute_path = config.chart_dir_path / filename
    relative_path = f"./{config.task2.chart_dir.rstrip('/')}/{filename}"
    return absolute_path, relative_path


def _numeric_value(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return 0.0
    return float(str(value))


def generate_chart(
    question_id: str,
    query_result: dict[str, object],
    config: str | Task2Config = "config.yaml",
    requested_chart: str | None = None,
    metric_name: str | None = None,
) -> dict[str, object]:
    loaded_config = load_task2_config(config) if isinstance(config, str) else config
    rules_module = importlib.import_module("src.task2.chart_rules")
    choose_chart_type = getattr(rules_module, "choose_chart_type")

    rows = cast(list[dict[str, object]], query_result.get("rows") or [])
    if (
        not loaded_config.task2.enable_charts
        or not isinstance(rows, list)
        or len(rows) <= 1
    ):
        return {
            "chart_type": "none",
            "image": [],
            "skipped_reason": "结果不足以生成图表",
        }

    chart_type = choose_chart_type(query_result, requested_chart)
    if chart_type == "none":
        return {"chart_type": "none", "image": [], "skipped_reason": "按规则无需绘图"}

    font_name = _find_font_name(loaded_config)
    if font_name is None:
        return {
            "chart_type": "none",
            "image": [],
            "skipped_reason": "未找到可用中文字体",
        }

    plt.rcParams["font.sans-serif"] = [font_name]
    plt.rcParams["axes.unicode_minus"] = False
    columns = [
        str(column) for column in cast(list[object], query_result.get("columns") or [])
    ]
    metric_columns = [
        column
        for column in columns
        if column not in {"stock_abbr", "report_period", "report_year"}
    ]
    if not metric_columns:
        return {
            "chart_type": "none",
            "image": [],
            "skipped_reason": "没有可绘制的数值列",
        }
    metric_column = metric_columns[0]
    display_metric = metric_name or metric_column

    absolute_path, relative_path = _chart_path(loaded_config, question_id, 1)
    figure, axis = plt.subplots(figsize=(8, 4.5))
    try:
        if chart_type == "line":
            x_values = [
                str(row.get("report_period") or row.get("report_year") or "")
                for row in rows
            ]
            y_values = [_numeric_value(row.get(metric_column)) for row in rows]
            axis.plot(x_values, y_values, marker="o")
            axis.set_xlabel("报告期")
            axis.set_ylabel(display_metric)
        elif chart_type == "bar":
            x_values = [
                str(row.get("report_period") or row.get("stock_abbr") or "")
                for row in rows
            ]
            y_values = [_numeric_value(row.get(metric_column)) for row in rows]
            axis.bar(x_values, y_values)
            axis.set_ylabel(display_metric)
        elif chart_type == "pie":
            x_values = [
                str(row.get("report_period") or row.get("stock_abbr") or "")
                for row in rows
            ]
            y_values = [_numeric_value(row.get(metric_column)) for row in rows]
            axis.pie(y_values, labels=x_values, autopct="%1.1f%%")
        else:
            axis.axis("off")
            table_rows = [
                [str(row.get(column) or "") for column in columns] for row in rows
            ]
            axis.table(cellText=table_rows, colLabels=columns, loc="center")

        axis.set_title(f"{question_id} {display_metric}")
        figure.tight_layout()
        figure.savefig(absolute_path, format="jpg", dpi=180)
    finally:
        plt.close(figure)

    return {"chart_type": chart_type, "image": [relative_path], "skipped_reason": None}
