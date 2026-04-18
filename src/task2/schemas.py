from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import cast


ATTACHMENT7_COLUMNS = ("编号", "问题", "SQL查询语句", "图形格式", "回答")


class ChartType(str, Enum):
    NONE = "none"
    LINE = "line"
    BAR = "bar"
    PIE = "pie"
    TABLE = "table"


def to_jsonable(value: object, *, drop_none: bool = False) -> object:
    if isinstance(value, Enum):
        return cast(object, value.value)
    if isinstance(value, dict):
        payload: dict[str, object] = {}
        raw_mapping = cast(dict[object, object], value)
        for key, item in raw_mapping.items():
            converted = to_jsonable(item, drop_none=drop_none)
            if drop_none and converted is None:
                continue
            payload[str(key)] = converted
        return payload
    if isinstance(value, list):
        raw_list = cast(list[object], value)
        items = [to_jsonable(item, drop_none=drop_none) for item in raw_list]
        return [item for item in items if not (drop_none and item is None)]
    if isinstance(value, tuple):
        raw_tuple = cast(tuple[object, ...], value)
        return [to_jsonable(item, drop_none=drop_none) for item in raw_tuple]
    return value


@dataclass(slots=True)
class AnswerPayload:
    content: str
    image: list[str] = field(default_factory=list)
    references: list[dict[str, object]] | None = None

    def to_dict(self) -> dict[str, object]:
        payload = {
            "content": self.content,
            "image": self.image or None,
            "references": self.references,
        }
        return cast(dict[str, object], to_jsonable(payload, drop_none=True))


@dataclass(slots=True)
class ClarificationDecision:
    needs_clarification: bool
    question: str | None = None
    missing_fields: tuple[str, ...] = ()
    defaulted_periods: tuple[str, ...] = ()
    reason: str | None = None


@dataclass(slots=True)
class ResolvedContext:
    question: str
    stock_code: str | None = None
    stock_abbr: str | None = None
    report_period: str | None = None
    report_year: int | None = None
    metric_name: str | None = None
    metric_column: str | None = None
    table_name: str | None = None
    intent: str = "single_value"
    missing_fields: tuple[str, ...] = ()
    defaulted_periods: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(slots=True)
class SqlPlan:
    intent: str
    question: str
    needs_clarification: bool = False
    clarification_question: str | None = None
    sql: str | None = None
    table_name: str | None = None
    metric_name: str | None = None
    metric_column: str | None = None
    chart_recommendation: ChartType = ChartType.NONE
    analysis_focus: tuple[str, ...] = ()
    defaulted_periods: tuple[str, ...] = ()
    planner_source: str = "heuristic"
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class ValidatedSql:
    accepted: bool
    normalized_sql: str
    table_name: str | None = None
    selected_columns: tuple[str, ...] = ()
    limit: int | None = None
    reason: str | None = None


@dataclass(slots=True)
class QueryResult:
    status: str
    sql: str
    columns: tuple[str, ...]
    rows: list[dict[str, object]]
    row_count: int
    message: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class ChartArtifact:
    chart_type: ChartType = ChartType.NONE
    image: list[str] = field(default_factory=list)
    title: str | None = None
    skipped_reason: str | None = None


@dataclass(slots=True)
class ConversationTurn:
    Q: str
    A: AnswerPayload

    def to_dict(self) -> dict[str, object]:
        return {"Q": self.Q, "A": self.A.to_dict()}


@dataclass(slots=True)
class SessionState:
    history: list[ConversationTurn] = field(default_factory=list)
    pending_context: ResolvedContext | None = None
    pending_slots: tuple[str, ...] = ()
    last_plan: SqlPlan | None = None
    last_images: list[str] = field(default_factory=list)
    turn_count: int = 0


@dataclass(slots=True)
class TurnResult:
    question: str
    answer: AnswerPayload
    resolved_context: ResolvedContext | None = None
    clarification: ClarificationDecision | None = None
    plan: SqlPlan | None = None
    validated_sql: ValidatedSql | None = None
    query_result: QueryResult | None = None
    chart: ChartArtifact | None = None
    error_code: str | None = None


@dataclass(slots=True)
class ConversationRecord:
    question_id: str
    turns: list[ConversationTurn] = field(default_factory=list)
    sql_queries: list[str] = field(default_factory=list)
    chart_type: str = "无"

    def to_attachment7(self) -> list[dict[str, object]]:
        return [turn.to_dict() for turn in self.turns]

    def questions_json(self) -> str:
        return json.dumps([{"Q": turn.Q} for turn in self.turns], ensure_ascii=False)

    def answers_json(self) -> str:
        return json.dumps(self.to_attachment7(), ensure_ascii=False)


@dataclass(slots=True)
class ExportRow:
    question_id: str
    question_payload: str
    sql_query: str
    chart_format: str
    answer_payload: str

    def to_dict(self) -> dict[str, str]:
        return {
            "编号": self.question_id,
            "问题": self.question_payload,
            "SQL查询语句": self.sql_query,
            "图形格式": self.chart_format,
            "回答": self.answer_payload,
        }
