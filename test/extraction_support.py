import csv
import json
import sys
from pathlib import Path
from typing import Any

import pymysql
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pdfExtractor.db_handler import DBHandler
from pdfExtractor.field_extractor import FieldExtractor
from pdfExtractor.main import process_pdf
from pdfExtractor.pdf_parser import PDFParser

FIXTURE_FILES = [
    "600080_20240427_0WKP.pdf",
    "600080_20240817_5X5X.pdf",
    "华润三九：2023年年度报告.pdf",
    "华润三九：2024年一季度报告.pdf",
]
DEFAULT_GOLDEN_PATH = Path(__file__).with_name("golden_key_fields.json")
TABLES = [
    "income_sheet",
    "balance_sheet",
    "cash_flow_sheet",
    "core_performance_indicators_sheet",
]


def fixture_pdf_paths(pdf_dir: str | Path) -> list[Path]:
    base = Path(pdf_dir)
    return [base / name for name in FIXTURE_FILES if (base / name).exists()]


def sanitize_filename(name: str) -> str:
    return name.replace("：", "_").replace(":", "_").replace("/", "_").replace(" ", "_")


def load_golden(golden_path: str | Path = DEFAULT_GOLDEN_PATH) -> dict[str, Any]:
    with open(golden_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _db_config(config_path: str | Path) -> dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    return config["database"]


def raw_connection(config_path: str | Path = ROOT / "config.yaml", *, autocommit=True):
    db_cfg = _db_config(config_path)
    return pymysql.connect(
        host=db_cfg["host"],
        port=int(db_cfg["port"]),
        user=db_cfg["user"],
        password=db_cfg.get("password", ""),
        database=db_cfg["database"],
        autocommit=autocommit,
        cursorclass=pymysql.cursors.DictCursor,
        charset="utf8mb4",
    )


def fixture_keys(golden: dict[str, Any]) -> list[tuple[str, str]]:
    return [
        (fixture["stock_code"], fixture["report_period"])
        for fixture in golden["fixtures"]
    ]


def cleanup_fixture_rows(
    config_path: str | Path = ROOT / "config.yaml",
    *,
    golden_path: str | Path = DEFAULT_GOLDEN_PATH,
) -> None:
    golden = load_golden(golden_path)
    pairs = fixture_keys(golden)
    conn = raw_connection(config_path, autocommit=True)
    try:
        with conn.cursor() as cursor:
            for table in TABLES:
                for stock_code, report_period in pairs:
                    cursor.execute(
                        f"DELETE FROM `{table}` WHERE stock_code=%s AND report_period=%s",
                        (stock_code, report_period),
                    )
    finally:
        conn.close()


def extract_single_pdf(pdf_path: str | Path) -> dict[str, Any]:
    pdf_path = Path(pdf_path)
    parser = PDFParser(str(pdf_path))
    extractor = FieldExtractor(parser)
    try:
        result: dict[str, Any] = {
            "filename": pdf_path.name,
            "metadata": {
                "stock_code": extractor.stock_code,
                "stock_abbr": extractor.stock_abbr,
                "report_period": extractor.report_period,
                "report_year": extractor.report_year,
            },
            "section_pages": {
                key: [
                    page + 1
                    for page in extractor._section_pages(keyword, max_pages=max_pages)
                ]
                for key, (keyword, max_pages) in extractor._SECTION_KEYWORDS.items()
            },
            "statements": {
                "income_sheet": extractor.extract_income_sheet(),
                "balance_sheet": extractor.extract_balance_sheet(),
                "cash_flow_sheet": extractor.extract_cash_flow_sheet(),
                "core_performance_indicators_sheet": extractor.extract_core_indicators(),
            },
            "diagnostics": extractor.diagnostics,
        }
        for key, (keyword, max_pages) in extractor._SECTION_KEYWORDS.items():
            inspected = extractor.inspect_section_rows(keyword, max_pages=max_pages)
            result.setdefault("row_stats", {})[key] = {
                "accepted": sum(1 for row in inspected if row.get("accepted")),
                "rejected": sum(1 for row in inspected if not row.get("accepted")),
                "sample_rows": [
                    {
                        "page": row.get("page", 0) + 1,
                        "row_name": row.get("row_name"),
                        "note_ref": row.get("note_ref"),
                        "numeric_cells": row.get("numeric_cells", [])[:3],
                        "accepted": row.get("accepted"),
                        "reason": row.get("reason"),
                    }
                    for row in inspected[:10]
                ],
            }
        return result
    finally:
        parser.close()


def write_errors_log(error_log: list[dict[str, Any]], output_dir: str | Path) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    error_log_path = output_dir / "errors.log"
    with open(error_log_path, "w", encoding="utf-8") as handle:
        if error_log:
            for error in error_log:
                handle.write(json.dumps(error, ensure_ascii=False) + "\n")
        else:
            handle.write("No errors\n")
    return error_log_path


def run_pipeline(
    pdf_dir: str | Path,
    output_dir: str | Path,
    *,
    config_path: str | Path = ROOT / "config.yaml",
    golden_path: str | Path = DEFAULT_GOLDEN_PATH,
    cleanup=True,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if cleanup:
        cleanup_fixture_rows(config_path=config_path, golden_path=golden_path)

    db = DBHandler(config_path=str(config_path))
    db.connect()
    error_log: list[dict[str, Any]] = []
    success_count = 0
    try:
        for pdf_path in fixture_pdf_paths(pdf_dir):
            if process_pdf(str(pdf_path), db, error_log):
                success_count += 1
        db.export_all_tables(str(output_dir))
    finally:
        db.close()

    error_log_path = write_errors_log(error_log, output_dir)
    return {
        "success_count": success_count,
        "total": len(fixture_pdf_paths(pdf_dir)),
        "errors": error_log,
        "error_log_path": str(error_log_path),
        "output_dir": str(output_dir),
    }


def load_csv_rows(output_dir: str | Path, table: str) -> list[dict[str, str]]:
    csv_path = Path(output_dir) / f"{table}.csv"
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def coerce_float(value: Any) -> float | None:
    if value in (None, "", "None"):
        return None
    return float(value)


def keyed_rows(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    result = {}
    for row in rows:
        result[(row["stock_code"], row["report_period"])] = row
    return result
