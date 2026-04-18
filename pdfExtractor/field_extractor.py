import logging
import re
from difflib import SequenceMatcher
from typing import Any, Callable

from pdfExtractor.pdf_parser import PDFParser
from pdfExtractor.utils import calculate_yoy_growth

logger = logging.getLogger(__name__)


class FieldExtractor:
    _META_KEYS = {"stock_code", "stock_abbr", "report_period", "report_year"}
    _SECTION_KEYWORDS = {
        "income": ("合并利润表", 8),
        "balance": ("合并资产负债表", 8),
        "cashflow": ("合并现金流量表", 8),
        "core": ("主要会计数据", 6),
    }
    _ALIASES = {
        "income": {
            "total_operating_revenue": [
                "营业总收入",
                "一、营业总收入",
                "营业收入",
                "一、营业收入",
                "其中：营业收入",
                "其中:营业收入",
                "主营业务收入",
            ],
            "net_profit": [
                "净利润",
                "五、净利润",
                "归属于母公司所有者的净利润",
                "归属于母公司股东的净利润",
                "归属于上市公司股东的净利润",
            ],
            "other_income": ["其他收益", "加：其他收益", "加:其他收益"],
            "operating_expense_cost_of_sales": [
                "营业成本",
                "减：营业成本",
                "减:营业成本",
                "其中：营业成本",
                "其中:营业成本",
            ],
            "operating_expense_selling_expenses": ["销售费用"],
            "operating_expense_administrative_expenses": ["管理费用"],
            "operating_expense_financial_expenses": ["财务费用"],
            "operating_expense_rnd_expenses": ["研发费用"],
            "operating_expense_taxes_and_surcharges": ["税金及附加"],
            "total_operating_expenses": [
                "营业总成本",
                "二、营业总成本",
                "营业成本合计",
            ],
            "operating_profit": ["营业利润", "三、营业利润"],
            "total_profit": ["利润总额", "四、利润总额"],
            "asset_impairment_loss": ["资产减值损失"],
            "credit_impairment_loss": ["信用减值损失"],
        },
        "balance": {
            "asset_cash_and_cash_equivalents": ["货币资金"],
            "asset_accounts_receivable": ["应收账款"],
            "asset_inventory": ["存货"],
            "asset_trading_financial_assets": ["交易性金融资产"],
            "asset_construction_in_progress": ["在建工程"],
            "asset_total_assets": ["资产总计", "总资产"],
            "liability_accounts_payable": ["应付账款"],
            "liability_advance_from_customers": ["预收款项", "合同负债"],
            "liability_total_liabilities": ["负债合计", "总负债"],
            "liability_contract_liabilities": ["合同负债"],
            "liability_short_term_loans": ["短期借款"],
            "equity_unappropriated_profit": ["未分配利润"],
            "equity_total_equity": [
                "所有者权益合计",
                "所有者权益(或股东权益)合计",
                "股东权益合计",
                "归属于母公司所有者权益(或股东权益)合计",
                "归属于母公司所有者权益合计",
                "归属于上市公司股东的所有者权益",
                "归属于上市公司股东的净资产",
            ],
        },
        "cashflow": {
            "net_cash_flow": [
                "现金及现金等价物净增加额",
                "五、现金及现金等价物净增加额",
                "现金净增加额",
            ],
            "operating_cf_net_amount": ["经营活动产生的现金流量净额"],
            "investing_cf_net_amount": ["投资活动产生的现金流量净额"],
            "financing_cf_net_amount": ["筹资活动产生的现金流量净额"],
            "operating_cf_cash_from_sales": ["销售商品、提供劳务收到的现金"],
            "investing_cf_cash_for_investments": ["投资支付的现金"],
            "investing_cf_cash_from_investment_recovery": ["收回投资收到的现金"],
            "financing_cf_cash_from_borrowing": ["取得借款收到的现金"],
            "financing_cf_cash_for_debt_repayment": ["偿还债务支付的现金"],
        },
        "core": {
            "eps": ["基本每股收益", "基本每股收益（元/股）", "基本每股收益(元/股)"],
            "roe": ["加权平均净资产收益率", "净资产收益率", "ROE"],
            "roe_weighted_excl_non_recurring": [
                "扣除非经常性损益后的加权平均净资产收益率"
            ],
            "net_profit_excl_non_recurring": [
                "扣除非经常性损益后的净利润",
                "归属于上市公司股东的扣除非经常性损益的净利润",
            ],
            "equity_parent": [
                "归属于母公司所有者权益(或股东权益)合计",
                "归属于母公司所有者权益合计",
                "归属于上市公司股东的净资产",
            ],
            "share_capital": ["实收资本（或股本）", "实收资本(或股本)", "股本"],
        },
    }
    _NOISE_PATTERNS = [
        r"^项目$",
        r"^附注$",
        r"^单位[:：]",
        r"币种[:：]",
        r"公司负责人",
        r"主管会计工作负责人",
        r"会计机构负责人",
        r"^本期发生额$",
        r"^上期发生额$",
        r"^期末余额$",
        r"^期初余额$",
        r"^本报告期$",
        r"^上年同期$",
        r"^本报告期比上年同期增减",
        r"^股票种类$",
        r"^股票上市交易所$",
        r"^股票简称$",
        r"^股票代码$",
        r"^办公地址$",
        r"^签字会计师姓名$",
        r"^持续督导的期间$",
    ]

    def __init__(self, parser: PDFParser):
        self.parser = parser
        self.stock_code, self.stock_abbr = parser.get_stock_info()
        self.report_period, self.report_year = parser.get_report_period()
        self.diagnostics: list[dict[str, Any]] = []
        self._rows_cache: dict[str, list[dict[str, Any]]] = {}
        self._inspection_cache: dict[str, list[dict[str, Any]]] = {}
        self._statement_cache: dict[str, dict[str, Any] | None] = {}
        self._statement_rows_cache: list[dict[str, Any]] | None = None
        self._core_rows_cache: list[dict[str, Any]] | None = None

        if not self.stock_code:
            self._record_diagnostic("metadata", "missing_stock_code")
        if not self.stock_abbr:
            self._record_diagnostic("metadata", "missing_stock_abbr")
        if not self.report_period:
            self._record_diagnostic("metadata", "missing_report_period")

    def _record_diagnostic(self, stage: str, reason: str, **context: Any) -> None:
        payload = {"stage": stage, "reason": reason}
        if context:
            payload.update(context)
        self.diagnostics.append(payload)

    @staticmethod
    def _normalize_text(text: str | None) -> str:
        value = (text or "").replace("\n", " ").replace("\r", " ").strip()
        value = value.replace("（", "(").replace("）", ")")
        value = value.replace("：", ":")
        return re.sub(r"\s+", " ", value)

    @staticmethod
    def _clean_field_name(name: str | None) -> str:
        value = FieldExtractor._normalize_text(name)
        value = value.replace(" ", "")
        replacements = [
            "其中:",
            "其中：",
            "项目",
            "本期发生额",
            "上期发生额",
            "期末余额",
            "期初余额",
            "本报告期",
            "上年同期",
            "归属于上市公司股东的",
            "归属于母公司股东的",
            "归属于母公司所有者的",
        ]
        for item in replacements:
            value = value.replace(item, "")
        return value

    @staticmethod
    def _similarity(a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        return SequenceMatcher(None, a, b).ratio()

    @staticmethod
    def _looks_like_note_reference(value: str | None) -> bool:
        text = FieldExtractor._normalize_text(value).replace(" ", "")
        if not text:
            return False
        return bool(
            re.fullmatch(r"[一二三四五六七八九十百零〇]{1,6}[、.．]\d{1,4}", text)
            or re.fullmatch(r"\([一二三四五六七八九十百零〇]{1,6}\)", text)
            or re.fullmatch(r"（[一二三四五六七八九十百零〇]{1,6}）", text)
        )

    def _looks_like_leading_note_reference(
        self, cell: str, remaining_cells: list[str]
    ) -> bool:
        normalized = self._normalize_text(cell).replace(" ", "")
        if self._looks_like_note_reference(normalized):
            return True
        if not re.fullmatch(r"\d{1,3}", normalized):
            return False

        later_numbers = []
        for item in remaining_cells:
            num = self._parse_number_silent(item)
            if num is not None:
                later_numbers.append(num)
        if not later_numbers:
            return False
        return any(abs(num) >= 1000 for num in later_numbers)

    def _valid_identity(self) -> bool:
        return bool(self.stock_code and self.report_period)

    @staticmethod
    def _parse_number_silent(value: str) -> float | None:
        if not value:
            return None
        s = str(value).strip()
        if FieldExtractor._looks_like_note_reference(s):
            return None
        if not re.search(r"\d", s):
            return None
        s = s.replace(",", "").replace("，", "").replace(" ", "")
        s = s.replace("－", "-").replace("%", "")
        if re.fullmatch(r"\(.*\)", s):
            s = "-" + s[1:-1]
        if re.fullmatch(r"（.*）", s):
            s = "-" + s[1:-1]
        s = re.sub(r"[^0-9.\-]", "", s)
        if s in {"", "-", ".", "-."}:
            return None
        try:
            return float(s)
        except ValueError:
            return None

    def _base_data(self, fields: list[str]) -> dict[str, Any]:
        data: dict[str, Any] = {
            "stock_code": self.stock_code,
            "stock_abbr": self.stock_abbr,
            "report_period": self.report_period,
            "report_year": self.report_year,
        }
        for field in fields:
            data[field] = None
        return data

    def _finalize_data(self, data: dict[str, Any] | None) -> dict[str, Any] | None:
        if not data:
            return None
        deduped = self._deduplicate_fields(data)
        if not deduped:
            return None
        has_payload = any(
            value is not None
            for key, value in deduped.items()
            if key not in self._META_KEYS
        )
        if not has_payload:
            return None
        return deduped

    def _deduplicate_fields(self, data: dict[str, Any] | None) -> dict[str, Any] | None:
        if not data:
            return data

        field_values: dict[str, Any] = {}
        for key, value in data.items():
            if value is not None and key not in self._META_KEYS:
                if key not in field_values:
                    field_values[key] = value

        result = {
            "stock_code": data.get("stock_code"),
            "stock_abbr": data.get("stock_abbr"),
            "report_period": data.get("report_period"),
            "report_year": data.get("report_year"),
        }
        result.update(field_values)
        return result

    @staticmethod
    def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
        if numerator is None or denominator in (None, 0):
            return None
        return round(numerator / denominator * 100, 4)

    def _sanitize_derived_metric(
        self, field_name: str, value: float | None, max_abs: float
    ) -> float | None:
        if value is None:
            return None
        if abs(value) > max_abs:
            self._record_diagnostic(
                "derived_metric",
                "value_out_of_range",
                field=field_name,
                value=value,
                max_abs=max_abs,
            )
            return None
        return round(value, 4)

    @staticmethod
    def _page_unit_to_wan(page_text: str) -> float:
        text = page_text or ""
        if "单位：亿元" in text or "单位:亿元" in text:
            return 10000.0
        if "单位：万元" in text or "单位:万元" in text:
            return 1.0
        if "单位：千元" in text or "单位:千元" in text:
            return 0.1
        return 0.0001

    def _section_pages(self, keyword: str, max_pages: int = 8) -> list[int]:
        regions = self.parser.get_section_regions(keyword, max_pages=max_pages)
        return [region["page_index"] for region in regions]

    def _split_tail_cells(self, cells: list[str]) -> tuple[str | None, list[str]]:
        note_ref = None
        numeric_cells: list[str] = []

        for idx, cell in enumerate(cells):
            if not cell:
                continue
            if (
                idx == 0
                and note_ref is None
                and self._looks_like_leading_note_reference(cell, cells[idx + 1 :])
            ):
                note_ref = cell
                continue
            if self._looks_like_note_reference(cell):
                if note_ref is None:
                    note_ref = cell
                continue

            if self._parse_number_silent(cell) is not None:
                numeric_cells.append(cell)

        return (note_ref, numeric_cells)

    def _row_priority(self, row_name_clean: str) -> int:
        priority = 0
        if row_name_clean.startswith("其中"):
            priority -= 2
        if ("持续经营" in row_name_clean) or ("终止经营" in row_name_clean):
            priority -= 2
        return priority

    def _is_noise_row(self, row_name: str) -> bool:
        clean = self._clean_field_name(row_name)
        if not clean:
            return True
        if len(clean) > 80:
            return True
        for pattern in self._NOISE_PATTERNS:
            if re.search(pattern, clean):
                return True
        return False

    def _build_row_record(
        self,
        raw_row: list[Any],
        page_idx: int,
        unit_to_wan: float,
        keyword: str,
    ) -> dict[str, Any] | None:
        cleaned = [self._normalize_text(cell) for cell in raw_row if cell is not None]
        cleaned = [cell for cell in cleaned if cell]
        if not cleaned:
            return None

        row_name = ""
        row_name_idx = -1
        for idx, cell in enumerate(cleaned):
            if self._looks_like_note_reference(cell):
                continue
            if self._parse_number_silent(cell) is None:
                row_name = cell
                row_name_idx = idx
                break

        if not row_name:
            return {
                "accepted": False,
                "reason": "no_label",
                "page": page_idx,
                "keyword": keyword,
                "raw_cells": cleaned,
            }

        tail_cells = [
            cell for idx, cell in enumerate(cleaned) if idx != row_name_idx and cell
        ]
        note_ref, numeric_cells = self._split_tail_cells(tail_cells)
        row = {
            "accepted": True,
            "reason": "ok",
            "row_name": row_name,
            "row_name_clean": self._clean_field_name(row_name),
            "note_ref": note_ref,
            "numeric_cells": numeric_cells,
            "unit_to_wan": unit_to_wan,
            "page": page_idx,
            "keyword": keyword,
            "raw_cells": cleaned,
        }

        if self._is_noise_row(row_name):
            row["accepted"] = False
            row["reason"] = "noise_row"
            return row
        if not numeric_cells:
            row["accepted"] = False
            row["reason"] = "no_numeric_values"
            return row
        return row

    def _extract_rows_from_regions(
        self,
        regions: list[dict[str, Any]],
        keyword: str,
        include_rejected: bool = False,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        pdf = self.parser._require_pdf()
        for region in regions:
            page_idx = region["page_index"]
            page = pdf.pages[page_idx]
            top = float(region.get("top", 0.0))
            bottom = float(region.get("bottom", page.height))
            work_page = page
            if top > 0 or bottom < page.height:
                work_page = page.crop((0, top, page.width, bottom))

            page_text = self.parser.get_page_text(page_idx)
            unit_to_wan = self._page_unit_to_wan(page_text)
            try:
                tables = work_page.extract_tables() or []
            except Exception:
                tables = []

            for table in tables:
                for raw_row in table:
                    if not raw_row:
                        continue
                    row = self._build_row_record(
                        raw_row, page_idx, unit_to_wan, keyword
                    )
                    if row is None:
                        continue
                    if row.get("accepted") or include_rejected:
                        rows.append(row)
        return rows

    def inspect_section_rows(
        self, keyword: str, max_pages: int = 8
    ) -> list[dict[str, Any]]:
        cache_key = f"inspect:{keyword}:{max_pages}"
        if cache_key in self._inspection_cache:
            return self._inspection_cache[cache_key]
        regions = self.parser.get_section_regions(keyword, max_pages=max_pages)
        rows = self._extract_rows_from_regions(regions, keyword, include_rejected=True)
        self._inspection_cache[cache_key] = rows
        return rows

    def _get_rows(
        self, cache_key: str, keyword: str, max_pages: int = 8
    ) -> list[dict[str, Any]]:
        if cache_key in self._rows_cache:
            return self._rows_cache[cache_key]
        regions = self.parser.get_section_regions(keyword, max_pages=max_pages)
        section_rows = self._extract_rows_from_regions(regions, keyword)
        self._rows_cache[cache_key] = section_rows
        return section_rows

    def _statement_rows(self) -> list[dict[str, Any]]:
        if self._statement_rows_cache is None:
            rows: list[dict[str, Any]] = []
            for cache_key in ("income", "balance", "cashflow"):
                keyword, max_pages = self._SECTION_KEYWORDS[cache_key]
                rows.extend(self._get_rows(cache_key, keyword, max_pages=max_pages))
            self._statement_rows_cache = rows
        return self._statement_rows_cache

    def _core_and_statement_rows(self) -> list[dict[str, Any]]:
        if self._core_rows_cache is None:
            keyword, max_pages = self._SECTION_KEYWORDS["core"]
            self._core_rows_cache = self._get_rows("core", keyword, max_pages=max_pages)
        return self._core_rows_cache + self._statement_rows()

    def _extract_numeric_pair(
        self, value_cells: list[str], unit_to_wan: float, convert_to_wan: bool
    ) -> tuple[float | None, float | None]:
        values: list[float] = []
        for cell in value_cells:
            num = self._parse_number_silent(cell)
            if num is None:
                continue
            if convert_to_wan:
                num = round(num * unit_to_wan, 2)
            values.append(num)
            if len(values) >= 2:
                break

        if not values:
            return (None, None)
        if len(values) == 1:
            return (values[0], None)
        return (values[0], values[1])

    def _score_alias_match(
        self, row_name_clean: str, aliases: list[str]
    ) -> tuple[float, int, int, str | None]:
        best_tuple: tuple[float, int, int] | None = None
        best_alias: str | None = None

        for idx, alias in enumerate(aliases):
            alias_clean = self._clean_field_name(alias)
            if not alias_clean:
                continue
            score = self._similarity(row_name_clean, alias_clean)
            exact_hit = 0
            if row_name_clean == alias_clean:
                score = max(score, 1.0)
                exact_hit = 1
            elif alias_clean in row_name_clean:
                score = max(score, 0.95)
                exact_hit = 1

            rank = (score, exact_hit, -idx)
            if best_tuple is None or rank > best_tuple:
                best_tuple = rank
                best_alias = alias

        if best_tuple is None:
            return (0.0, 0, 999, None)
        return (best_tuple[0], best_tuple[1], -best_tuple[2], best_alias)

    def _match_field_from_rows(
        self,
        rows: list[dict[str, Any]],
        aliases: list[str],
        convert_to_wan: bool = True,
        threshold: float = 0.66,
        required_keywords: list[str] | None = None,
        exact_only: bool = False,
        row_filter: Callable[[dict[str, Any]], bool] | None = None,
    ) -> dict[str, Any] | None:
        candidates = []
        for row in rows:
            if not row.get("accepted", True):
                continue
            if row_filter and not row_filter(row):
                continue
            row_name = row.get("row_name", "")
            if required_keywords and not any(
                keyword in row_name for keyword in required_keywords
            ):
                continue

            row_name_clean = row.get("row_name_clean") or self._clean_field_name(
                row_name
            )
            if not row_name_clean:
                continue

            score, exact_hit, alias_index, matched_alias = self._score_alias_match(
                row_name_clean, aliases
            )
            if exact_only and not exact_hit:
                continue
            if score < threshold:
                continue

            current, previous = self._extract_numeric_pair(
                row.get("numeric_cells", []),
                row.get("unit_to_wan", 0.0001),
                convert_to_wan=convert_to_wan,
            )
            if current is None and previous is None:
                continue

            candidates.append(
                {
                    "row": row,
                    "score": score,
                    "exact_hit": exact_hit,
                    "alias_index": alias_index,
                    "matched_alias": matched_alias,
                    "current": current,
                    "previous": previous,
                    "priority": self._row_priority(row_name_clean),
                }
            )

        if not candidates:
            return None

        candidates.sort(
            key=lambda item: (
                item["exact_hit"],
                item["score"],
                item["priority"],
                1 if item["current"] is not None else 0,
                -item["alias_index"],
                -int(item["row"].get("page", 0)),
            ),
            reverse=True,
        )

        best = candidates[0]
        second = candidates[1] if len(candidates) > 1 else None
        unique = second is None or (
            best["exact_hit"] > second["exact_hit"]
            or best["score"] - second["score"] >= 0.03
            or best["alias_index"] < second["alias_index"]
        )
        result = dict(best)
        result["unique"] = unique
        result["candidate_count"] = len(candidates)
        return result

    def _extract_field(
        self,
        section_rows: list[dict[str, Any]],
        aliases: list[str],
        *,
        field_name: str,
        convert_to_wan: bool = True,
        required_keywords: list[str] | None = None,
        fallback_rows: list[dict[str, Any]] | None = None,
        row_filter: Callable[[dict[str, Any]], bool] | None = None,
    ) -> tuple[float | None, float | None]:
        primary = self._match_field_from_rows(
            section_rows,
            aliases,
            convert_to_wan=convert_to_wan,
            required_keywords=required_keywords,
            row_filter=row_filter,
        )
        if primary and (primary["exact_hit"] or primary["score"] >= 0.78):
            return (primary["current"], primary["previous"])

        fallback_rows = fallback_rows or self._statement_rows()
        fallback = self._match_field_from_rows(
            fallback_rows,
            aliases,
            convert_to_wan=convert_to_wan,
            threshold=0.9,
            required_keywords=required_keywords,
            exact_only=True,
            row_filter=row_filter,
        )
        if fallback and fallback.get("unique"):
            row = fallback["row"]
            self._record_diagnostic(
                "field_match",
                "controlled_fallback",
                field=field_name,
                page=int(row.get("page", 0)) + 1,
                row_name=row.get("row_name"),
                score=round(float(fallback["score"]), 4),
            )
            return (fallback["current"], fallback["previous"])

        self._record_diagnostic(
            "field_match",
            "missing_field",
            field=field_name,
            primary_score=round(float(primary["score"]), 4) if primary else None,
        )
        return (None, None)

    def _statement(self, cache_key: str, builder: Callable[[], dict[str, Any] | None]):
        if cache_key not in self._statement_cache:
            self._statement_cache[cache_key] = builder()
        return self._statement_cache[cache_key]

    def _build_income_sheet(self):
        if not self._valid_identity():
            self._record_diagnostic("metadata", "invalid_identity_for_income")
            logger.error("Missing stock_code/report_period, skip income_sheet")
            return None

        data = self._base_data(
            [
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
            ]
        )

        rows = self._get_rows("income", *self._SECTION_KEYWORDS["income"])
        aliases = self._ALIASES["income"]

        revenue_cur, revenue_prev = self._extract_field(
            rows,
            aliases["total_operating_revenue"],
            field_name="total_operating_revenue",
        )
        net_cur, net_prev = self._extract_field(
            rows, aliases["net_profit"], field_name="net_profit"
        )
        data["total_operating_revenue"] = revenue_cur
        data["operating_revenue_yoy_growth"] = calculate_yoy_growth(
            revenue_cur, revenue_prev
        )
        data["net_profit"] = net_cur
        data["net_profit_yoy_growth"] = calculate_yoy_growth(net_cur, net_prev)

        for key, alias_values in aliases.items():
            if key in {"total_operating_revenue", "net_profit"}:
                continue
            value, _ = self._extract_field(rows, alias_values, field_name=key)
            data[key] = value

        return self._finalize_data(data)

    def extract_income_sheet(self):
        return self._statement("income", self._build_income_sheet)

    def _build_balance_sheet(self):
        if not self._valid_identity():
            self._record_diagnostic("metadata", "invalid_identity_for_balance")
            logger.error("Missing stock_code/report_period, skip balance_sheet")
            return None

        data = self._base_data(
            [
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
                "asset_liability_ratio",
                "equity_unappropriated_profit",
                "equity_total_equity",
            ]
        )

        rows = self._get_rows("balance", *self._SECTION_KEYWORDS["balance"])
        aliases = self._ALIASES["balance"]

        for key, alias_values in aliases.items():
            value, previous = self._extract_field(rows, alias_values, field_name=key)
            data[key] = value
            if key == "asset_total_assets":
                data["asset_total_assets_yoy_growth"] = calculate_yoy_growth(
                    value, previous
                )
            if key == "liability_total_liabilities":
                data["liability_total_liabilities_yoy_growth"] = calculate_yoy_growth(
                    value, previous
                )

        total_assets = data.get("asset_total_assets")
        total_liabilities = data.get("liability_total_liabilities")
        data["asset_liability_ratio"] = self._sanitize_derived_metric(
            "asset_liability_ratio",
            self._safe_ratio(total_liabilities, total_assets),
            max_abs=1000,
        )

        if (
            data.get("equity_total_equity") is None
            and total_assets is not None
            and total_liabilities is not None
        ):
            data["equity_total_equity"] = round(total_assets - total_liabilities, 2)

        return self._finalize_data(data)

    def extract_balance_sheet(self):
        return self._statement("balance", self._build_balance_sheet)

    def _build_cash_flow_sheet(self):
        if not self._valid_identity():
            self._record_diagnostic("metadata", "invalid_identity_for_cashflow")
            logger.error("Missing stock_code/report_period, skip cash_flow_sheet")
            return None

        data = self._base_data(
            [
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
            ]
        )

        rows = self._get_rows("cashflow", *self._SECTION_KEYWORDS["cashflow"])
        aliases = self._ALIASES["cashflow"]

        net_cur, net_prev = self._extract_field(
            rows, aliases["net_cash_flow"], field_name="net_cash_flow"
        )
        op_cur, _ = self._extract_field(
            rows,
            aliases["operating_cf_net_amount"],
            field_name="operating_cf_net_amount",
        )
        inv_cur, _ = self._extract_field(
            rows,
            aliases["investing_cf_net_amount"],
            field_name="investing_cf_net_amount",
        )
        fin_cur, _ = self._extract_field(
            rows,
            aliases["financing_cf_net_amount"],
            field_name="financing_cf_net_amount",
        )

        data["net_cash_flow"] = net_cur
        data["net_cash_flow_yoy_growth"] = calculate_yoy_growth(net_cur, net_prev)
        data["operating_cf_net_amount"] = op_cur
        data["investing_cf_net_amount"] = inv_cur
        data["financing_cf_net_amount"] = fin_cur

        for key in [
            "operating_cf_cash_from_sales",
            "investing_cf_cash_for_investments",
            "investing_cf_cash_from_investment_recovery",
            "financing_cf_cash_from_borrowing",
            "financing_cf_cash_for_debt_repayment",
        ]:
            value, _ = self._extract_field(rows, aliases[key], field_name=key)
            data[key] = value

        data["operating_cf_ratio_of_net_cf"] = self._sanitize_derived_metric(
            "operating_cf_ratio_of_net_cf",
            self._safe_ratio(op_cur, net_cur),
            max_abs=1000,
        )
        data["investing_cf_ratio_of_net_cf"] = self._sanitize_derived_metric(
            "investing_cf_ratio_of_net_cf",
            self._safe_ratio(inv_cur, net_cur),
            max_abs=1000,
        )
        data["financing_cf_ratio_of_net_cf"] = self._sanitize_derived_metric(
            "financing_cf_ratio_of_net_cf",
            self._safe_ratio(fin_cur, net_cur),
            max_abs=1000,
        )

        return self._finalize_data(data)

    def extract_cash_flow_sheet(self):
        return self._statement("cashflow", self._build_cash_flow_sheet)

    def _build_core_indicators(self):
        if not self._valid_identity():
            self._record_diagnostic("metadata", "invalid_identity_for_core")
            logger.error("Missing stock_code/report_period, skip core_indicators")
            return None

        income = self.extract_income_sheet() or {}
        balance = self.extract_balance_sheet() or {}
        cashflow = self.extract_cash_flow_sheet() or {}

        core_rows = self._get_rows("core", *self._SECTION_KEYWORDS["core"])
        fallback_rows = self._core_and_statement_rows()
        core_alias = self._ALIASES["core"]

        def non_recurring_row_filter(row: dict[str, Any]) -> bool:
            numeric_cells = row.get("numeric_cells", [])
            if len(numeric_cells) <= 3:
                return True
            raw = " ".join(row.get("raw_cells", []))
            return "%" in raw

        eps, _ = self._extract_field(
            core_rows,
            core_alias["eps"],
            field_name="eps",
            convert_to_wan=False,
            fallback_rows=fallback_rows,
        )
        roe, _ = self._extract_field(
            core_rows,
            core_alias["roe"],
            field_name="roe",
            convert_to_wan=False,
            required_keywords=["收益率", "ROE", "%"],
            fallback_rows=fallback_rows,
        )
        roe_excl, _ = self._extract_field(
            core_rows,
            core_alias["roe_weighted_excl_non_recurring"],
            field_name="roe_weighted_excl_non_recurring",
            convert_to_wan=False,
            required_keywords=["收益率", "ROE", "%"],
            fallback_rows=fallback_rows,
        )
        net_excl_cur, net_excl_prev = self._extract_field(
            core_rows,
            core_alias["net_profit_excl_non_recurring"],
            field_name="net_profit_excl_non_recurring",
            convert_to_wan=True,
            fallback_rows=fallback_rows,
            row_filter=non_recurring_row_filter,
        )

        balance_rows = self._get_rows("balance", *self._SECTION_KEYWORDS["balance"])
        equity_parent_yuan, _ = self._extract_field(
            balance_rows,
            core_alias["equity_parent"],
            field_name="equity_parent",
            convert_to_wan=False,
            fallback_rows=self._statement_rows(),
        )
        share_capital_yuan, _ = self._extract_field(
            balance_rows,
            core_alias["share_capital"],
            field_name="share_capital",
            convert_to_wan=False,
            fallback_rows=self._statement_rows(),
        )

        net_asset_per_share = None
        if equity_parent_yuan is not None and share_capital_yuan not in (None, 0):
            net_asset_per_share = self._sanitize_derived_metric(
                "net_asset_per_share",
                round(equity_parent_yuan / share_capital_yuan, 4),
                max_abs=10000,
            )

        operating_cf_per_share = None
        op_cf_wan = cashflow.get("operating_cf_net_amount")
        if op_cf_wan is not None and share_capital_yuan not in (None, 0):
            operating_cf_per_share = self._sanitize_derived_metric(
                "operating_cf_per_share",
                round((op_cf_wan * 10000) / share_capital_yuan, 4),
                max_abs=10000,
            )

        revenue_wan = income.get("total_operating_revenue")
        net_profit_wan = income.get("net_profit")
        cost_wan = income.get("operating_expense_cost_of_sales")

        gross_profit_margin = None
        if revenue_wan not in (None, 0) and cost_wan is not None:
            gross_profit_margin = self._sanitize_derived_metric(
                "gross_profit_margin",
                round((revenue_wan - cost_wan) / revenue_wan * 100, 4),
                max_abs=1000,
            )

        net_profit_margin = None
        if revenue_wan not in (None, 0) and net_profit_wan is not None:
            net_profit_margin = self._sanitize_derived_metric(
                "net_profit_margin",
                round(net_profit_wan / revenue_wan * 100, 4),
                max_abs=1000,
            )

        data = {
            "stock_code": self.stock_code,
            "stock_abbr": self.stock_abbr,
            "report_period": self.report_period,
            "report_year": self.report_year,
            "eps": eps,
            "total_operating_revenue": revenue_wan,
            "operating_revenue_yoy_growth": income.get("operating_revenue_yoy_growth"),
            "operating_revenue_qoq_growth": None,
            "net_profit_10k_yuan": net_profit_wan,
            "net_profit_yoy_growth": income.get("net_profit_yoy_growth"),
            "net_profit_qoq_growth": None,
            "net_asset_per_share": net_asset_per_share,
            "roe": roe,
            "operating_cf_per_share": operating_cf_per_share,
            "net_profit_excl_non_recurring": net_excl_cur,
            "net_profit_excl_non_recurring_yoy": calculate_yoy_growth(
                net_excl_cur, net_excl_prev
            ),
            "gross_profit_margin": gross_profit_margin,
            "net_profit_margin": net_profit_margin,
            "roe_weighted_excl_non_recurring": roe_excl,
        }

        return self._finalize_data(data)

    def extract_core_indicators(self):
        return self._statement("core", self._build_core_indicators)
