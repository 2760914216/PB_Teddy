# pyright: reportMissingImports=false
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pdfExtractor.db_handler import DBHandler


def main():
    db = DBHandler("config.yaml")
    db.connect()
    try:
        db.begin()
        data = {
            "stock_code": "999998",
            "stock_abbr": "空值样本",
            "report_period": "2099Q1",
            "report_year": 2099,
            "eps": 0.1,
            "total_operating_revenue": 1.0,
            "operating_revenue_yoy_growth": None,
            "operating_revenue_qoq_growth": None,
            "net_profit_10k_yuan": 1.0,
            "net_profit_yoy_growth": None,
            "net_profit_qoq_growth": None,
            "net_asset_per_share": None,
            "roe": None,
            "operating_cf_per_share": None,
            "net_profit_excl_non_recurring": None,
            "net_profit_excl_non_recurring_yoy": None,
            "gross_profit_margin": None,
            "net_profit_margin": None,
            "roe_weighted_excl_non_recurring": None,
        }
        db.insert_core_indicators(data, commit=False)
        print("nullable metrics accepted")
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    main()
