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


def _load_metric_catalog() -> tuple[dict[str, str], ...]:
    importlib.import_module("src.task2.resolver")

    from .resolver import METRIC_CATALOG

    return METRIC_CATALOG


def _load_company_catalog(config) -> tuple[tuple[str, str], ...]:
    importlib.import_module("src.task2.resolver")

    from .resolver import _load_company_catalog as load_catalog

    config_path = str(config.config_path)
    result: tuple[tuple[str, str], ...] = ()
    try:
        result = load_catalog(config_path)
    except Exception:
        pass
    return result


def build_clarification_prompt(
    question: str,
    resolved_context: dict[str, object],
    config="config.yaml",
) -> tuple[str, str]:
    """Build prompts for LLM-driven intent clarification.

    Returns:
        (system_prompt, user_prompt) tuple for LLM clarification decision.
    """
    if isinstance(config, str):
        from .config import load_task2_config

        config = load_task2_config(config)

    metric_catalog = _load_metric_catalog()
    company_catalog = _load_company_catalog(config)
    company_list = ", ".join(f"{code}({abbr})" for code, abbr in company_catalog[:50])
    if len(company_catalog) > 50:
        company_list += f" 等{len(company_catalog)}家公司"

    schema_hint = {
        "needs_clarification": True,
        "question": "请补充您要查询的公司名称或财务指标",
        "missing_fields": ["missing_company", "missing_metric"],
    }
    system_prompt = (
        "你是中文财报意图澄清助手。当用户查询意图模糊、关键信息缺失时，应主动追问引导用户补充信息。"
        "需要澄清的典型场景："
        "1. 缺少公司名称（用户未说明要查询哪家公司）"
        "2. 缺少财务指标（用户未说明要看什么指标，如利润、营收等）"
        "3. 缺少时间范围（用户未说明查询哪个报告期）"
        "4. 意图不明（无法确定要查趋势还是单值）"
        "5. 公司不在数据库中（用户说的公司不在可查询范围内）"
        "6. 指标不在数据库中（用户说的指标不可用）"
        "追问要求："
        "1. 每次只追问最关键的1-2个缺失信息"
        "2. 问题要自然流畅，使用中文"
        "3. 如果公司不在库中，应说明可用公司列表并请用户确认"
        "4. 如果指标不在库中，应推荐相似可用指标"
    )
    resolved_json = json.dumps(resolved_context, ensure_ascii=False)
    metric_catalog_json = json.dumps(metric_catalog, ensure_ascii=False)
    user_prompt = (
        f"用户问题：{question}\n"
        f"已解析上下文：{resolved_json}\n"
        f"可用财务指标目录：{metric_catalog_json}\n"
        f"数据库中已有的公司示例：{company_list}\n"
        f"输出 JSON 结构示例：{json.dumps(schema_hint, ensure_ascii=False)}\n"
        "请判断已解析上下文是否足以生成有效SQL查询。"
        "如果信息不足，设置 needs_clarification=true 并给出需要补充的问题；"
        "否则设置 needs_clarification=false。"
    )
    return system_prompt, user_prompt


def build_probe_prompt(question_id: str, question: str) -> tuple[str, str]:
    system_prompt = (
        "你是中文财报问答模型探针。请输出一个 JSON 对象，字段包括 sql、analysis、chart_recommendation。"
        "sql 必须是单条 SELECT；analysis 必须是中文。"
    )
    user_prompt = f"题号：{question_id}\n问题：{question}\n请直接输出 JSON。"
    return system_prompt, user_prompt
