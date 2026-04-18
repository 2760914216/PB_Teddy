# pyright: reportMissingImports=false
import pdfplumber  # type: ignore[import-not-found, reportMissingImports]
import logging
import os
import re
from pdfExtractor.utils import extract_stock_info, parse_report_period

logger = logging.getLogger(__name__)


SECTION_HEADERS = [
    "合并利润表",
    "合并资产负债表",
    "合并现金流量表",
    "母公司利润表",
    "母公司资产负债表",
    "母公司现金流量表",
    "合并所有者权益变动表",
    "母公司所有者权益变动表",
]


class PDFParser:
    def __init__(self, pdf_path):
        """Open PDF with pdfplumber.
        Store: self.pdf, self.filename, self.pdf_path
        """
        self.pdf_path = pdf_path
        self.filename = os.path.basename(pdf_path)
        self.pdf = pdfplumber.open(pdf_path)
        self._full_text_cache = None
        self._page_texts = {}
        logger.info(f"Opened PDF: {self.filename} ({len(self.pdf.pages)} pages)")

    def _require_pdf(self):
        if self.pdf is None:
            raise RuntimeError("PDF is already closed")
        return self.pdf

    def get_page_text(self, page_num):
        """Get text from a specific page (0-indexed). Cache results."""
        pdf = self._require_pdf()
        if page_num not in self._page_texts:
            page = pdf.pages[page_num]
            self._page_texts[page_num] = page.extract_text() or ""
        return self._page_texts[page_num]

    @staticmethod
    def _looks_like_toc_page(text):
        snippet = (text or "")[:1200]
        if "目录" not in snippet:
            return False
        return (snippet.count("……") >= 2) or (snippet.count("....") >= 2)

    def _metadata_page_indices(self, max_pages=8):
        pdf = self._require_pdf()
        indices = []
        for i in range(min(max_pages, len(pdf.pages))):
            text = self.get_page_text(i)
            if self._looks_like_toc_page(text):
                continue
            indices.append(i)
        return indices or list(range(min(max_pages, len(pdf.pages))))

    def _first_search_match(self, page_num, keyword):
        pdf = self._require_pdf()
        page = pdf.pages[page_num]
        try:
            matches = page.search(keyword) or []
        except Exception:
            matches = []
        if not matches:
            return None
        return min(matches, key=lambda item: item.get("top", 0))

    def get_full_text(self):
        """Extract all text from all pages. Cache result."""
        pdf = self._require_pdf()
        if self._full_text_cache is None:
            texts = []
            for i in range(len(pdf.pages)):
                texts.append(self.get_page_text(i))
            self._full_text_cache = "\n".join(texts)
        return self._full_text_cache

    def find_section_pages(self, keyword):
        """Find page numbers (0-indexed) containing a keyword.
        Returns list of page indices.
        """
        pdf = self._require_pdf()
        pages = []
        skipped_toc_pages = []
        for i in range(len(pdf.pages)):
            text = self.get_page_text(i)
            if keyword in text:
                if i < 12 and self._looks_like_toc_page(text):
                    skipped_toc_pages.append(i)
                    continue
                pages.append(i)
        return pages or skipped_toc_pages

    def get_section_regions(self, keyword, max_pages=8):
        pages = self.find_section_pages(keyword)
        if not pages:
            return []

        start_page = pages[0]
        stop_headers = [header for header in SECTION_HEADERS if header != keyword]
        pdf = self._require_pdf()
        regions = []

        for i in range(start_page, min(start_page + max_pages, len(pdf.pages))):
            page = pdf.pages[i]
            top = 0.0
            bottom = float(page.height)

            if i == start_page:
                start_match = self._first_search_match(i, keyword)
                if start_match is not None:
                    top = max(top, float(start_match.get("bottom", 0)))

            stop_top = None
            for stop_header in stop_headers:
                stop_match = self._first_search_match(i, stop_header)
                if stop_match is None:
                    continue
                stop_top = (
                    float(stop_match.get("top", 0))
                    if stop_top is None
                    else min(stop_top, float(stop_match.get("top", 0)))
                )

            if stop_top is not None:
                bottom = min(bottom, stop_top)

            if bottom - top > 6:
                regions.append({"page_index": i, "top": top, "bottom": bottom})

            if stop_top is not None and i >= start_page:
                break

        return regions

    def get_section_text(self, keyword, max_pages=5):
        """Get text from pages containing keyword and subsequent pages.
        Financial tables often span multiple pages.
        Returns concatenated text from the section.

        Strategy:
        1. Find first page with keyword
        2. Include that page and up to max_pages-1 subsequent pages
        3. Stop if we hit another major section header
        """
        pages = self.find_section_pages(keyword)
        if not pages:
            logger.warning(f"Section '{keyword}' not found in {self.filename}")
            return ""

        start_page = pages[0]
        section_texts = []

        section_headers = [
            "合并利润表",
            "合并资产负债表",
            "合并现金流量表",
            "母公司利润表",
            "母公司资产负债表",
            "母公司现金流量表",
            "合并所有者权益变动表",
            "母公司所有者权益变动表",
        ]
        stop_headers = [h for h in section_headers if h != keyword]

        pdf = self._require_pdf()
        for i in range(start_page, min(start_page + max_pages, len(pdf.pages))):
            text = self.get_page_text(i)
            section_texts.append(text)
            # After adding this page, check if it contains a stop header
            # (don't check the first page — it contains the keyword itself)
            if i > start_page:
                for header in stop_headers:
                    if header in text:
                        return "\n".join(section_texts)

        return "\n".join(section_texts)

    def get_stock_info(self):
        """Extract stock code and abbreviation from first few pages.
        Returns (stock_code, stock_abbr)
        """
        pdf = self._require_pdf()
        stock_code = None
        stock_abbr = None

        for i in self._metadata_page_indices(max_pages=10):
            text = self.get_page_text(i)
            code, abbr = extract_stock_info(text, self.filename)

            if not code:
                full_text_code = re.search(
                    r"(?:公司代码|证券代码|股票代码)[：:\s]*(\d{6})", text
                )
                if full_text_code:
                    code = full_text_code.group(1)
            if not abbr:
                full_text_abbr = re.search(
                    r"(?:公司简称|证券简称|股票简称)[：:\s]*([^\s\n]+)", text
                )
                if full_text_abbr:
                    abbr = full_text_abbr.group(1).strip()

            stock_code = stock_code or code
            stock_abbr = stock_abbr or abbr
            if stock_code and stock_abbr:
                return (stock_code, stock_abbr)

        for i in range(min(20, len(pdf.pages))):
            text = self.get_page_text(i)
            code, abbr = extract_stock_info(text, self.filename)
            stock_code = stock_code or code
            stock_abbr = stock_abbr or abbr
            if stock_code and stock_abbr:
                return (stock_code, stock_abbr)

        code, abbr = extract_stock_info("", self.filename)
        stock_code = stock_code or code
        stock_abbr = stock_abbr or abbr
        return (stock_code, stock_abbr)

    def get_report_period(self):
        """Determine report period from content.
        Returns (report_period, report_year) e.g. ("2023FY", 2023)
        """
        pdf = self._require_pdf()
        text = ""
        for i in self._metadata_page_indices(max_pages=8):
            text += self.get_page_text(i) + "\n"
        return parse_report_period(text, self.filename)

    def close(self):
        """Close PDF."""
        if self.pdf:
            self.pdf.close()
            self.pdf = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
