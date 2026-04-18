# pyright: reportMissingImports=false
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pdfExtractor.field_extractor import FieldExtractor


REQUIRED = {
    "income": {
        "total_operating_revenue": ["营业总收入", "营业收入"],
        "net_profit": ["净利润", "归属于上市公司股东的净利润"],
    },
    "balance": {
        "asset_total_assets": ["资产总计", "总资产"],
        "equity_total_equity": ["所有者权益(或股东权益)合计"],
    },
    "cashflow": {
        "net_cash_flow": ["现金及现金等价物净增加额"],
        "operating_cf_net_amount": ["经营活动产生的现金流量净额"],
    },
    "core": {
        "eps": ["基本每股收益"],
        "share_capital": ["实收资本(或股本)", "股本"],
    },
}


def main():
    failures = []
    for table, fields in REQUIRED.items():
        for field, aliases in fields.items():
            current = FieldExtractor._ALIASES[table][field]
            print(table, field, current)
            for alias in aliases:
                if alias not in current:
                    failures.append(f"missing alias {table}.{field}: {alias}")

    if failures:
        for failure in failures:
            print("FAIL", failure)
        sys.exit(1)


if __name__ == "__main__":
    main()
