from __future__ import annotations

import importlib
from typing import Protocol, cast

from .config import Task2Config, load_task2_config


class _SessionLike(Protocol):
    pending_context: dict[str, object] | None
    last_context: dict[str, object] | None
    pending_slots: list[str]
    last_plan: dict[str, object] | None
    last_images: list[str]

    def record_turn(
        self,
        question: str,
        answer: dict[str, object],
        *,
        sql: str | None = None,
    ) -> None: ...

    def clear_pending(self) -> None: ...


def handle_turn(
    session: _SessionLike,
    question: str,
    *,
    config: str | Task2Config = "config.yaml",
    question_id: str = "BCLI001",
    use_llm: bool = True,
) -> dict[str, object]:
    loaded_config = load_task2_config(config) if isinstance(config, str) else config
    nl2sql_module = importlib.import_module("src.task2.nl2sql")
    query_service_module = importlib.import_module("src.task2.query_service")
    analysis_module = importlib.import_module("src.task2.analysis")
    charting_module = importlib.import_module("src.task2.charting")
    answer_module = importlib.import_module("src.task2.answer_formatter")

    build_sql_plan = getattr(nl2sql_module, "build_sql_plan")
    execute_sql_plan = getattr(query_service_module, "execute_sql_plan")
    compose_analysis = getattr(analysis_module, "compose_analysis")
    generate_chart = getattr(charting_module, "generate_chart")
    format_answer = getattr(answer_module, "format_answer")

    previous_context = session.pending_context or session.last_context
    plan = build_sql_plan(question, loaded_config, previous_context, use_llm=use_llm)
    resolved_context = dict(plan.get("resolved_context") or {})
    if bool(plan.get("needs_clarification")):
        clarification_question = str(
            plan.get("clarification_question") or "请补充查询信息。"
        )
        answer = format_answer(clarification_question)
        session.pending_context = resolved_context
        session.last_context = resolved_context
        session.pending_slots = list(resolved_context.get("missing_fields") or [])
        session.last_plan = plan
        session.record_turn(question, answer)
        return {
            "question": question,
            "answer": answer,
            "plan": plan,
            "query_result": None,
            "chart": {"chart_type": "none", "image": []},
        }

    query_result = execute_sql_plan(plan, loaded_config)
    chart = generate_chart(
        question_id,
        query_result,
        loaded_config,
        str(plan.get("chart_recommendation") or "none"),
        str(resolved_context.get("metric_name") or ""),
    )
    analysis = compose_analysis(question, resolved_context, query_result)
    answer = format_answer(analysis, chart)

    session.record_turn(question, answer, sql=str(query_result.get("sql") or ""))
    session.last_plan = plan
    session.last_context = resolved_context
    session.last_images = list(chart.get("image") or [])
    session.clear_pending()
    return {
        "question": question,
        "answer": answer,
        "plan": plan,
        "query_result": query_result,
        "chart": chart,
    }


def run_conversation(
    question_id: str,
    turns: list[str],
    *,
    config: str | Task2Config = "config.yaml",
    use_llm: bool = True,
) -> dict[str, object]:
    session_module = importlib.import_module("src.task2.session")
    session_class = getattr(session_module, "Task2Session")
    answer_module = importlib.import_module("src.task2.answer_formatter")
    format_answer = getattr(answer_module, "format_answer")

    session = cast(_SessionLike, session_class())
    turn_results: list[dict[str, object]] = []
    for question in turns:
        turn_results.append(
            handle_turn(
                session,
                question,
                config=config,
                question_id=question_id,
                use_llm=use_llm,
            )
        )

    answers = []
    for item in turn_results:
        answer = item.get("answer")
        if not isinstance(answer, dict):
            answer = format_answer(str(answer or ""))
        answers.append({"Q": item.get("question", ""), "A": answer})

    return {
        "question_id": question_id,
        "turns": answers,
        "sql_queries": [
            str(
                cast(dict[str, object], item.get("query_result") or {}).get("sql") or ""
            )
            for item in turn_results
            if isinstance(item.get("query_result"), dict)
        ],
        "chart_type": next(
            (
                str(
                    cast(dict[str, object], item.get("chart") or {}).get("chart_type")
                    or "无"
                )
                for item in turn_results
                if isinstance(item.get("chart"), dict)
                and cast(dict[str, object], item.get("chart") or {}).get("chart_type")
                not in {None, "none"}
            ),
            "无",
        ),
    }
