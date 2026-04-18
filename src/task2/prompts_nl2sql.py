from __future__ import annotations

import importlib
import json


def _table_columns() -> dict[str, tuple[str, ...]]:
    guardrails = importlib.import_module("src.task2.sql_guardrails")
    return dict(getattr(guardrails, "TABLE_COLUMNS"))


def build_nl2sql_prompt(
    question: str, resolved_context: dict[str, object], max_rows: int
) -> tuple[str, str]:
    table_columns = _table_columns()
    schema_hint = {
        "intent": "single_value | trend",
        "needs_clarification": False,
        "clarification_question": None,
        "sql": "SELECT ...",
        "chart_recommendation": "none | line | bar | pie | table",
        "analysis_focus": ["一句中文说明应该关注的数据点"],
    }
    system_prompt = (
        "你是中文财报 NL2SQL 规划器。只允许为单条 SELECT 生成结构化 JSON。"
        "禁止写入 SQL，禁止使用白名单之外的表和字段。"
        f"任何查询都必须考虑 LIMIT {max_rows}。"
    )
    user_prompt = (
        f"用户问题：{question}\n"
        f"已解析上下文：{json.dumps(resolved_context, ensure_ascii=False)}\n"
        f"白名单表字段：{json.dumps(table_columns, ensure_ascii=False)}\n"
        f"输出 JSON 结构示例：{json.dumps(schema_hint, ensure_ascii=False)}\n"
        "如果信息不足，请设置 needs_clarification=true 并给出中文追问；否则返回可执行 SQL。"
    )
    return system_prompt, user_prompt


def build_probe_prompt(question_id: str, question: str) -> tuple[str, str]:
    system_prompt = (
        "你是中文财报问答模型探针。请输出一个 JSON 对象，字段包括 sql、analysis、chart_recommendation。"
        "sql 必须是单条 SELECT；analysis 必须是中文。"
    )
    user_prompt = f"题号：{question_id}\n问题：{question}\n请直接输出 JSON。"
    return system_prompt, user_prompt
