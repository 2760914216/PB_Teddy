import logging
import os
from typing import Optional

import pandas as pd
import pymysql
import yaml

logger = logging.getLogger(__name__)


class DataValidationError(ValueError):
    def __init__(self, table: str, field: str, value, reason: str):
        self.table = table
        self.field = field
        self.value = value
        self.reason = reason
        super().__init__(f"{table}.{field}: {reason} (value={value})")


class DBHandler:
    _FIELD_MAX_ABS = {
        "income_sheet": {
            "net_profit_yoy_growth": 100000,
            "operating_revenue_yoy_growth": 100000,
        },
        "balance_sheet": {
            "asset_total_assets_yoy_growth": 100000,
            "liability_total_liabilities_yoy_growth": 100000,
            "asset_liability_ratio": 1000,
        },
        "cash_flow_sheet": {
            "net_cash_flow_yoy_growth": 100000,
            "operating_cf_ratio_of_net_cf": 1000,
            "investing_cf_ratio_of_net_cf": 1000,
            "financing_cf_ratio_of_net_cf": 1000,
        },
        "core_performance_indicators_sheet": {
            "eps": 10000,
            "operating_revenue_yoy_growth": 100000,
            "operating_revenue_qoq_growth": 100000,
            "net_profit_yoy_growth": 100000,
            "net_profit_qoq_growth": 100000,
            "net_asset_per_share": 10000,
            "roe": 1000,
            "operating_cf_per_share": 10000,
            "net_profit_excl_non_recurring_yoy": 100000,
            "gross_profit_margin": 1000,
            "net_profit_margin": 1000,
            "roe_weighted_excl_non_recurring": 1000,
        },
    }

    def __init__(self, config_path="config.yaml"):
        config_file = os.path.abspath(config_path)
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        except Exception:
            logger.exception("Failed to load DB config from %s", config_file)
            raise

        db_config = config.get("database", {})
        self.host = db_config.get("host", "localhost")
        self.port = int(db_config.get("port", 3306))
        self.user = db_config.get("user", "root")
        self.password = db_config.get("password", "")
        self.database = db_config.get("database")
        self.conn: Optional[pymysql.connections.Connection] = None

    def connect(self):
        try:
            self.conn = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                cursorclass=pymysql.cursors.DictCursor,
                charset="utf8mb4",
                autocommit=False,
            )
            return self.conn
        except Exception:
            logger.exception(
                "Failed to connect to MySQL %s:%s/%s",
                self.host,
                self.port,
                self.database,
            )
            raise

    def close(self):
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception:
                logger.exception("Failed to close MySQL connection")
                raise
            finally:
                self.conn = None

    def begin(self):
        self._ensure_connected()

    def commit(self):
        if self.conn is None:
            raise RuntimeError("Database connection is not available")
        self.conn.commit()

    def rollback(self):
        if self.conn is None:
            return
        self.conn.rollback()

    def _ensure_connected(self):
        if self.conn is None:
            self.connect()
            return

        try:
            self.conn.ping(reconnect=True)
        except Exception:
            logger.warning("MySQL connection lost, reconnecting")
            self.connect()

    def _validate_before_upsert(self, table, data):
        key_fields = ("stock_code", "report_period")
        for field in key_fields:
            if not data.get(field):
                raise DataValidationError(
                    table, field, data.get(field), "missing key field"
                )

        for field, max_abs in self._FIELD_MAX_ABS.get(table, {}).items():
            value = data.get(field)
            if value is None:
                continue
            if abs(float(value)) > max_abs:
                raise DataValidationError(
                    table,
                    field,
                    value,
                    f"absolute value exceeds guardrail {max_abs}",
                )

    def upsert(
        self,
        table,
        data,
        key_fields=("stock_code", "report_period"),
        *,
        commit=True,
    ):
        if not isinstance(data, dict) or not data:
            raise ValueError("data must be a non-empty dict")

        self._ensure_connected()
        self._validate_before_upsert(table, data)

        insert_data = {k: v for k, v in data.items() if k != "serial_number"}
        if not insert_data:
            raise ValueError("No insertable fields found in data")

        missing_key_fields = [field for field in key_fields if field not in insert_data]
        if missing_key_fields:
            raise KeyError(f"Missing key_fields in data: {missing_key_fields}")

        conn = self.conn
        if conn is None:
            raise RuntimeError("Database connection is not available")

        delete_where = " AND ".join([f"`{field}` = %s" for field in key_fields])
        delete_values = [insert_data[field] for field in key_fields]
        delete_sql = f"DELETE FROM `{table}` WHERE {delete_where}"

        columns = list(insert_data.keys())
        columns_sql = ", ".join([f"`{col}`" for col in columns])
        placeholders = ", ".join(["%s"] * len(columns))
        insert_sql = f"INSERT INTO `{table}` ({columns_sql}) VALUES ({placeholders})"
        insert_values = [insert_data[col] for col in columns]

        try:
            with conn.cursor() as cursor:
                cursor.execute(delete_sql, delete_values)
                cursor.execute(insert_sql, insert_values)
            if commit:
                conn.commit()
        except Exception:
            conn.rollback()
            logger.exception("Failed to upsert into table=%s", table)
            raise

    def insert_income_sheet(self, data, *, commit=True):
        self.upsert("income_sheet", data, commit=commit)

    def insert_balance_sheet(self, data, *, commit=True):
        self.upsert("balance_sheet", data, commit=commit)

    def insert_cash_flow_sheet(self, data, *, commit=True):
        self.upsert("cash_flow_sheet", data, commit=commit)

    def insert_core_indicators(self, data, *, commit=True):
        self.upsert("core_performance_indicators_sheet", data, commit=commit)

    def query(self, table, stock_code=None, report_period=None):
        self._ensure_connected()
        conn = self.conn
        if conn is None:
            raise RuntimeError("Database connection is not available")

        where_parts = []
        params = []
        if stock_code is not None:
            where_parts.append("`stock_code` = %s")
            params.append(stock_code)
        if report_period is not None:
            where_parts.append("`report_period` = %s")
            params.append(report_period)

        sql = f"SELECT * FROM `{table}`"
        if where_parts:
            sql += " WHERE " + " AND ".join(where_parts)

        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                return list(cursor.fetchall())
        except Exception:
            logger.exception("Failed to query table=%s", table)
            raise

    def export_to_csv(self, table, output_path):
        self._ensure_connected()
        conn = self.conn
        if conn is None:
            raise RuntimeError("Database connection is not available")

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        sql = f"SELECT * FROM `{table}`"
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                rows = cursor.fetchall()
                columns = [desc[0] for desc in cursor.description]
            df = pd.DataFrame(rows, columns=columns)
            df.to_csv(output_path, index=False, encoding="utf-8-sig")
        except Exception:
            logger.exception("Failed to export table=%s to csv=%s", table, output_path)
            raise

    def export_all_tables(self, output_dir):
        os.makedirs(output_dir, exist_ok=True)

        tables = [
            "income_sheet",
            "balance_sheet",
            "cash_flow_sheet",
            "core_performance_indicators_sheet",
        ]
        for table in tables:
            path = os.path.join(output_dir, f"{table}.csv")
            self.export_to_csv(table, path)
            logger.info(f"Exported {table} to {path}")
