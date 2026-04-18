# pyright: reportMissingImports=false
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pdfExtractor.db_handler import DBHandler, DataValidationError


def main():
    parser = argparse.ArgumentParser(description="Check pre-insert validation guard")
    parser.add_argument("--case", default="net_asset_per_share_overflow")
    args = parser.parse_args()

    db = DBHandler("config.yaml")
    db.connect()
    try:
        db.begin()
        data = {
            "stock_code": "999999",
            "stock_abbr": "校验样本",
            "report_period": "2099FY",
            "report_year": 2099,
            "eps": 1.0,
            "total_operating_revenue": 1.0,
            "net_profit_10k_yuan": 1.0,
            "net_asset_per_share": 99999999.0,
        }
        try:
            db.insert_core_indicators(data, commit=False)
        except DataValidationError as exc:
            print("rejected", exc.table, exc.field, exc.reason, exc.value)
            return
        raise SystemExit("FAIL guard did not reject overflow")
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    main()
