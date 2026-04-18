# pyright: reportMissingImports=false
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from extraction_support import cleanup_fixture_rows, raw_connection
from pdfExtractor.db_handler import DBHandler, DataValidationError
from pdfExtractor.field_extractor import FieldExtractor
from pdfExtractor.pdf_parser import PDFParser


def main():
    parser = argparse.ArgumentParser(description="Check per-PDF atomic rollback")
    parser.add_argument("--pdf", default="600080_20240427_0WKP.pdf")
    args = parser.parse_args()

    cleanup_fixture_rows()
    parser_obj = PDFParser(f"test_set/{args.pdf}")
    extractor = FieldExtractor(parser_obj)
    income = extractor.extract_income_sheet()
    balance = extractor.extract_balance_sheet()
    parser_obj.close()

    if not income or not balance:
        raise SystemExit("FAIL could not extract fixture data for atomicity check")

    db = DBHandler("config.yaml")
    db.connect()
    try:
        db.begin()
        db.insert_income_sheet(income, commit=False)
        raise DataValidationError(
            "core_performance_indicators_sheet",
            "net_asset_per_share",
            99999999.0,
            "forced rollback",
        )
    except DataValidationError as exc:
        print("forced failure", exc)
        db.rollback()
    finally:
        db.close()

    conn = raw_connection()
    try:
        with conn.cursor() as cursor:
            leaked = {}
            for table in [
                "income_sheet",
                "balance_sheet",
                "cash_flow_sheet",
                "core_performance_indicators_sheet",
            ]:
                cursor.execute(
                    f"SELECT COUNT(*) AS cnt FROM `{table}` WHERE stock_code=%s AND report_period=%s",
                    (income["stock_code"], income["report_period"]),
                )
                row = cursor.fetchone()
                leaked[table] = row["cnt"] if row is not None else 0
    finally:
        conn.close()

    print(leaked)
    if any(leaked.values()):
        print("FAIL partial rows leaked after rollback")
        sys.exit(1)


if __name__ == "__main__":
    main()
