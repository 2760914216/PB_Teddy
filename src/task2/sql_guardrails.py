from __future__ import annotations

from dataclasses import dataclass
import re
from typing import cast


@dataclass(slots=True)
class ValidatedSql:
    accepted: bool
    normalized_sql: str
    table_name: str | None = None
    selected_columns: tuple[str, ...] = ()
    limit: int | None = None
    reason: str | None = None


TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "income_sheet": (
        "stock_code",
        "stock_abbr",
        "report_period",
        "report_year",
        "net_profit",
        "net_profit_yoy_growth",
        "other_income",
        "total_operating_revenue",
        "operating_revenue_yoy_growth",
        "operating_expense_cost_of_sales",
        "operating_expense_selling_expenses",
        "operating_expense_administrative_expenses",
        "operating_expense_financial_expenses",
        "operating_expense_rnd_expenses",
        "operating_expense_taxes_and_surcharges",
        "total_operating_expenses",
        "operating_profit",
        "total_profit",
        "asset_impairment_loss",
        "credit_impairment_loss",
    ),
    "balance_sheet": (
        "stock_code",
        "stock_abbr",
        "report_period",
        "report_year",
        "asset_cash_and_cash_equivalents",
        "asset_accounts_receivable",
        "asset_inventory",
        "asset_trading_financial_assets",
        "asset_construction_in_progress",
        "asset_total_assets",
        "asset_total_assets_yoy_growth",
        "liability_accounts_payable",
        "liability_advance_from_customers",
        "liability_total_liabilities",
        "liability_total_liabilities_yoy_growth",
        "liability_contract_liabilities",
        "liability_short_term_loans",
        "equity_unappropriated_profit",
        "equity_total_equity",
        "asset_liability_ratio",
    ),
    "cash_flow_sheet": (
        "stock_code",
        "stock_abbr",
        "report_period",
        "report_year",
        "net_cash_flow",
        "net_cash_flow_yoy_growth",
        "operating_cf_net_amount",
        "operating_cf_ratio_of_net_cf",
        "operating_cf_cash_from_sales",
        "investing_cf_net_amount",
        "investing_cf_ratio_of_net_cf",
        "investing_cf_cash_for_investments",
        "investing_cf_cash_from_investment_recovery",
        "financing_cf_cash_from_borrowing",
        "financing_cf_cash_for_debt_repayment",
        "financing_cf_net_amount",
        "financing_cf_ratio_of_net_cf",
    ),
    "core_performance_indicators_sheet": (
        "stock_code",
        "stock_abbr",
        "report_period",
        "report_year",
        "eps",
        "total_operating_revenue",
        "operating_revenue_yoy_growth",
        "operating_revenue_qoq_growth",
        "net_profit_10k_yuan",
        "net_profit_yoy_growth",
        "net_profit_qoq_growth",
        "net_asset_per_share",
        "roe",
        "operating_cf_per_share",
        "net_profit_excl_non_recurring",
        "net_profit_excl_non_recurring_yoy",
        "gross_profit_margin",
        "net_profit_margin",
        "roe_weighted_excl_non_recurring",
    ),
}

SQL_FUNCTIONS = {"count", "sum", "avg", "min", "max", "abs", "round"}
SQL_KEYWORDS = {
    "select",
    "from",
    "where",
    "and",
    "or",
    "not",
    "like",
    "is",
    "null",
    "as",
    "order",
    "by",
    "asc",
    "desc",
    "limit",
    "case",
    "when",
    "then",
    "else",
    "end",
    "in",
    "between",
    "distinct",
}
FORBIDDEN_PATTERNS = (
    r";.+",
    r"--",
    r"/\*",
    r"\b(insert|update|delete|drop|truncate|alter|create|replace|grant|revoke|into|outfile|load_file|union|join)\b",
)


def allowed_tables() -> tuple[str, ...]:
    return tuple(TABLE_COLUMNS.keys())


def allowed_columns() -> dict[str, set[str]]:
    return {table: set(columns) for table, columns in TABLE_COLUMNS.items()}


def _normalize_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.strip()).rstrip(";")


def _split_select_columns(raw_columns: str) -> list[str]:
    columns: list[str] = []
    current: list[str] = []
    depth = 0
    for char in raw_columns:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        if char == "," and depth == 0:
            column = "".join(current).strip()
            if column:
                columns.append(column)
            current = []
            continue
        current.append(char)
    final_column = "".join(current).strip()
    if final_column:
        columns.append(final_column)
    return columns


def _extract_table_name(sql: str) -> str | None:
    matched = re.search(r"\bfrom\s+([a-z_][a-z0-9_]*)\b", sql, re.IGNORECASE)
    if not matched:
        return None
    return matched.group(1)


def _strip_alias(expression: str) -> str:
    return re.sub(r"\s+as\s+[a-z_][a-z0-9_]*$", "", expression, flags=re.IGNORECASE)


def _extract_alias(expression: str) -> str | None:
    matched = re.search(r"\s+as\s+([a-z_][a-z0-9_]*)$", expression, flags=re.IGNORECASE)
    if matched is None:
        return None
    return matched.group(1).lower()


def _extract_expression_columns(expression: str) -> tuple[str, ...]:
    bare = _strip_alias(expression.strip())
    if bare == "*":
        return ("*",)
    if re.fullmatch(r"count\s*\(\s*\*\s*\)", bare, re.IGNORECASE):
        return ()
    function_match = re.fullmatch(
        r"([a-z_][a-z0-9_]*)\s*\(\s*([a-z_][a-z0-9_]*)\s*\)",
        bare,
        re.IGNORECASE,
    )
    if function_match:
        function_name, column_name = function_match.groups()
        if function_name.lower() not in SQL_FUNCTIONS:
            return ("__invalid_function__",)
        return (column_name,)
    column_match = re.fullmatch(r"([a-z_][a-z0-9_]*)", bare, re.IGNORECASE)
    if column_match:
        return (column_match.group(1),)
    return ("__invalid_expression__",)


def _remove_string_literals(sql: str) -> str:
    return re.sub(r"'[^']*'", "''", sql)


def validate_sql(sql: str, *, default_limit: int = 50) -> ValidatedSql:
    normalized_sql = _normalize_sql(sql)
    if not normalized_sql:
        return ValidatedSql(False, normalized_sql, reason="SQL 不能为空")

    upper_sql = normalized_sql.upper()
    if not upper_sql.startswith("SELECT "):
        return ValidatedSql(False, normalized_sql, reason="SELECT only")
    if len(re.findall(r"\bSELECT\b", upper_sql)) != 1:
        return ValidatedSql(False, normalized_sql, reason="仅允许单条 SELECT 查询")

    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, normalized_sql, re.IGNORECASE):
            return ValidatedSql(False, normalized_sql, reason="包含危险关键字或多语句")

    table_name = _extract_table_name(normalized_sql)
    if table_name is None:
        return ValidatedSql(False, normalized_sql, reason="缺少 FROM 子句")
    if table_name not in TABLE_COLUMNS:
        return ValidatedSql(
            False, normalized_sql, table_name=table_name, reason="存在未授权表"
        )

    select_match = re.match(r"select\s+(.*?)\s+from\s+", normalized_sql, re.IGNORECASE)
    if not select_match:
        return ValidatedSql(
            False, normalized_sql, table_name=table_name, reason="无法解析 SELECT 列"
        )

    allowed = set(TABLE_COLUMNS[table_name])
    expressions = _split_select_columns(select_match.group(1))
    selected_columns: list[str] = []
    expression_aliases: set[str] = set()
    for expression in expressions:
        alias = _extract_alias(expression)
        if alias is not None:
            expression_aliases.add(alias)
        columns = _extract_expression_columns(expression)
        if "__invalid_expression__" in columns or "__invalid_function__" in columns:
            return ValidatedSql(
                False,
                normalized_sql,
                table_name=table_name,
                reason=f"不支持的表达式: {expression}",
            )
        for column_name in columns:
            if column_name == "*":
                selected_columns.extend(TABLE_COLUMNS[table_name])
                continue
            if column_name not in allowed:
                return ValidatedSql(
                    False,
                    normalized_sql,
                    table_name=table_name,
                    reason=f"存在未授权列: {column_name}",
                )
            selected_columns.append(column_name)

    sql_without_literals = _remove_string_literals(normalized_sql)
    tokens = cast(
        list[str],
        re.findall(r"\b[a-z_][a-z0-9_]*\b", sql_without_literals, re.IGNORECASE),
    )
    for token in tokens:
        lowered = token.lower()
        if (
            lowered in SQL_KEYWORDS
            or lowered in SQL_FUNCTIONS
            or lowered == table_name
            or lowered in expression_aliases
        ):
            continue
        if lowered not in allowed:
            return ValidatedSql(
                False,
                normalized_sql,
                table_name=table_name,
                reason=f"存在未授权标识符: {token}",
            )

    limit_match = re.search(r"\blimit\s+(\d+)\b", normalized_sql, re.IGNORECASE)
    final_limit = default_limit
    final_sql = normalized_sql
    if limit_match:
        final_limit = min(int(limit_match.group(1)), default_limit)
        final_sql = re.sub(
            r"\blimit\s+\d+\b",
            f"LIMIT {final_limit}",
            normalized_sql,
            flags=re.IGNORECASE,
        )
    else:
        final_sql = f"{normalized_sql} LIMIT {default_limit}"

    return ValidatedSql(
        accepted=True,
        normalized_sql=final_sql,
        table_name=table_name,
        selected_columns=tuple(dict.fromkeys(selected_columns)),
        limit=final_limit,
    )
