from __future__ import annotations

import json
import re
from typing import cast


def normalize_question_id(question_id: str) -> str:
    normalized = question_id.strip().upper()
    matched = re.fullmatch(r"B(\d{3})", normalized)
    if matched:
        return f"B1{matched.group(1)}"
    return normalized


def chart_format_label(chart_type: str | None) -> str:
    mapping = {
        None: "无",
        "": "无",
        "none": "无",
        "line": "折线图",
        "bar": "柱状图",
        "pie": "饼图",
        "table": "表格",
    }
    return mapping.get(chart_type, str(chart_type))


def _clean_answer(answer: dict[str, object]) -> dict[str, object]:
    payload = {"content": answer.get("content")}
    images = answer.get("image")
    if isinstance(images, list) and images:
        payload["image"] = [str(item) for item in cast(list[object], images)]
    references = answer.get("references")
    if isinstance(references, list) and references:
        payload["references"] = references
    return payload


def conversation_to_attachment7(record: dict[str, object]) -> list[dict[str, object]]:
    turns = record.get("turns") or []
    result: list[dict[str, object]] = []
    if not isinstance(turns, list):
        return result
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        answer = turn.get("A") or {}
        if not isinstance(answer, dict):
            answer = {"content": str(answer)}
        result.append(
            {
                "Q": str(turn.get("Q") or ""),
                "A": _clean_answer(cast(dict[str, object], answer)),
            }
        )
    return result


def conversation_to_export_row(record: dict[str, object]) -> dict[str, str]:
    question_id = normalize_question_id(str(record.get("question_id") or ""))
    turns = conversation_to_attachment7(record)
    questions = json.dumps([{"Q": item["Q"]} for item in turns], ensure_ascii=False)
    answers = json.dumps(turns, ensure_ascii=False)
    sql_queries = cast(list[object], record.get("sql_queries") or [])
    sql_text = "\n".join(str(item) for item in sql_queries if str(item).strip())
    chart_type = chart_format_label(str(record.get("chart_type") or "无"))
    return {
        "编号": question_id,
        "问题": questions,
        "SQL查询语句": sql_text,
        "图形格式": chart_type,
        "回答": answers,
    }
