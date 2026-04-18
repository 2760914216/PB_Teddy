from __future__ import annotations

import json


def build_intent_judge_prompt(
    question: str, resolved_context: dict[str, object]
) -> tuple[str, str, dict[str, object]]:
    schema_hint = {
        "status": "resolved | clarify | abstain",
        "confidence": 0.0,
        "clarification_question": None,
        "reason": "一句中文说明",
        "slot_updates": {
            "stock_code": None,
            "stock_abbr": None,
            "metric_name": None,
            "metric_column": None,
            "table_name": None,
        },
    }
    system_prompt = (
        "你是中文财报问答的意图澄清裁决器。"
        "你只能输出一个 JSON 对象，不允许输出 SQL、表结构解释、自然语言前后缀或 Markdown。"
        "你的职责仅限于：在候选公司/指标之间做保守裁决，或者生成中文追问。"
        "如果置信度不足，请返回 clarify 或 abstain，绝对不要猜测。"
        "slot_updates 只能填写候选集中已有的公司或指标值，不能发明新字段、新表、新列。"
    )
    user_prompt = (
        f"用户问题：{question}\n"
        f"规则解析上下文：{json.dumps(resolved_context, ensure_ascii=False)}\n"
        f"输出 JSON 示例：{json.dumps(schema_hint, ensure_ascii=False)}\n"
        "如果规则已经明确命中，请返回 abstain。"
        "如果候选仍有歧义但可以保守澄清，请返回 clarify 并给出一句中文追问。"
        "只有当候选集中存在唯一更合理选择且你有足够把握时，才返回 resolved。"
    )
    return system_prompt, user_prompt, schema_hint
