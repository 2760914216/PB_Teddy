from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Callable, Protocol, cast

import pymysql

from .config import Task2Config, load_task2_config


@dataclass(slots=True)
class QueryMetadata:
    columns: tuple[str, ...]
    row_count: int


class _ValidatedSqlLike(Protocol):
    accepted: bool
    normalized_sql: str
    reason: str | None


class ReadOnlyDBExecutor:
    config: Task2Config

    def __init__(self, config: str | Task2Config = "config.yaml"):
        self.config = load_task2_config(config) if isinstance(config, str) else config

    def _connect(self) -> pymysql.connections.Connection:
        try:
            return pymysql.connect(
                host=self.config.database.host,
                port=self.config.database.port,
                user=self.config.database.user,
                password=self.config.database.password,
                database=self.config.database.database,
                cursorclass=pymysql.cursors.DictCursor,
                charset="utf8mb4",
                autocommit=True,
            )
        except Exception as exc:  # noqa: BLE001
            raise self._task2_error(
                "DBExecutionError", f"数据库连接失败: {exc}"
            ) from exc

    def execute(self, sql: str | _ValidatedSqlLike) -> list[dict[str, object]]:
        rows, _ = self.execute_with_metadata(sql)
        return rows

    def execute_with_metadata(
        self, sql: str | _ValidatedSqlLike
    ) -> tuple[list[dict[str, object]], QueryMetadata]:
        validated = self._validate_sql(sql)
        if not validated.accepted:
            raise self._task2_error(
                "SQLGuardrailError", validated.reason or "SQL 校验未通过"
            )

        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                _ = cursor.execute(validated.normalized_sql)
                raw_rows = cursor.fetchall()
                rows = [dict(row) for row in raw_rows]
                description = cursor.description or ()
                columns = tuple(item[0] for item in description)
                metadata = QueryMetadata(columns=columns, row_count=len(rows))
                return rows, metadata
        except Exception as exc:  # noqa: BLE001
            raise self._task2_error("DBExecutionError", f"查询执行失败: {exc}") from exc
        finally:
            connection.close()

    def _validate_sql(self, sql: str | _ValidatedSqlLike) -> _ValidatedSqlLike:
        if isinstance(sql, str):
            guardrails = importlib.import_module("src.task2.sql_guardrails")
            validate_sql_fn = cast(
                Callable[[str], _ValidatedSqlLike], getattr(guardrails, "validate_sql")
            )
            return validate_sql_fn(sql)
        return sql

    def _task2_error(self, class_name: str, message: str) -> Exception:
        errors_module = importlib.import_module("src.task2.errors")
        error_class = cast(
            Callable[[str], Exception], getattr(errors_module, class_name)
        )
        return error_class(message)
