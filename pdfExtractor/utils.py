import logging
import os
import re

logger = logging.getLogger(__name__)


def _normalize_text(value):
    return re.sub(r"\s+", " ", (value or "").replace("\n", " ").strip())


def clean_number(value_str):
    """Clean a number string from PDF extraction.
    - Handle None/empty → return None
    - Remove commas and spaces
    - Handle parentheses as negative: (100) → -100
    - Handle full-width minus "－" → "-"
    - Return float or None on failure
    """
    if not value_str or (isinstance(value_str, str) and value_str.strip() == ""):
        return None
    value = str(value_str).replace(",", "").replace(" ", "").replace("，", "").strip()
    value = value.replace("－", "-")
    if "(" in value and ")" in value:
        value = "-" + value.replace("(", "").replace(")", "")
    if "（" in value and "）" in value:
        value = "-" + value.replace("（", "").replace("）", "")
    try:
        return float(value)
    except ValueError:
        logger.warning(f"Cannot parse number: {value_str}")
        return None


def yuan_to_wan(yuan_value):
    """Convert 元 to 万元 (divide by 10000), round to 2 decimal places.
    Returns None if input is None.
    """
    if yuan_value is None:
        return None
    return round(yuan_value / 10000, 2)


def _period_from_text(text):
    text = _normalize_text(text)

    explicit_patterns = [
        (r"(20\d{2})年(?:第?一季度|一季度)报告", "Q1"),
        (r"(20\d{2})年(?:第?三季度|三季度)报告", "Q3"),
        (r"(20\d{2})年(?:半年度报告|半年度|半年报|中报)", "HY"),
        (r"(20\d{2})年(?:年度报告)", "FY"),
    ]
    for pattern, suffix in explicit_patterns:
        match = re.search(pattern, text)
        if match:
            year = int(match.group(1))
            return (f"{year}{suffix}", year)

    year_match = re.search(r"(20\d{2})\s*年", text)
    if not year_match:
        year_match = re.search(r"(20\d{2})", text)
    if not year_match:
        return (None, None)

    year = int(year_match.group(1))

    if ("第一季度" in text) or ("一季度" in text):
        return (f"{year}Q1", year)
    if ("第三季度" in text) or ("三季度" in text):
        return (f"{year}Q3", year)
    if ("半年度" in text) or ("半年报" in text) or ("中报" in text):
        return (f"{year}HY", year)
    if ("年度报告" in text) and ("摘要" not in text[:800]):
        return (f"{year}FY", year)

    range_match = re.search(r"(20\d{2})年\s*\d{1,2}\s*[—\-至]\s*(\d{1,2})\s*月", text)
    if range_match:
        y = int(range_match.group(1))
        end_month = int(range_match.group(2))
        if end_month == 3:
            return (f"{y}Q1", y)
        if end_month == 6:
            return (f"{y}HY", y)
        if end_month == 9:
            return (f"{y}Q3", y)
        if end_month == 12:
            return (f"{y}FY", y)

    return (None, None)


def _period_from_filename(filename):
    name = os.path.basename(filename or "")
    period_match = re.search(
        r"(20\d{2})\s*年?\s*(第一季度|一季度|第三季度|三季度|半年度|半年报|中报|年度|Q1|Q3|HY|H1|FY)",
        name,
        flags=re.I,
    )
    if period_match:
        year = int(period_match.group(1))
        period_hint = period_match.group(2)
        if re.search(r"第一季度|一季度|Q1", period_hint, flags=re.I):
            return (f"{year}Q1", year)
        if re.search(r"第三季度|三季度|Q3", period_hint, flags=re.I):
            return (f"{year}Q3", year)
        if re.search(r"半年度|半年报|中报|HY|H1", period_hint, flags=re.I):
            return (f"{year}HY", year)
        if re.search(r"年度|FY", period_hint, flags=re.I):
            return (f"{year}FY", year)

    year_match = re.search(r"(20\d{2})\s*年", name)
    if not year_match:
        return (None, None)

    year = int(year_match.group(1))
    return (None, year)


def parse_report_period(pdf_text, filename=""):
    text = (pdf_text or "")[:20000]

    content_period, content_year = _period_from_text(text)
    filename_period, filename_year = _period_from_filename(filename)

    if content_period and filename_year and filename_year != content_year:
        logger.warning(
            "Filename year/content year mismatch: file=%s, content=%s (%s)",
            filename_year,
            content_year,
            filename,
        )

    if content_period and filename_period and filename_period != content_period:
        logger.warning(
            "Filename period/content period mismatch: file=%s, content=%s (%s)",
            filename_period,
            content_period,
            filename,
        )

    if content_period:
        return (content_period, content_year)

    if filename_period:
        logger.warning(
            "Falling back to filename-derived report period for %s: %s",
            filename,
            filename_period,
        )
        return (filename_period, filename_year)

    logger.error(
        "Cannot determine report period from PDF content or filename: %s", filename
    )
    return (None, None)


def extract_stock_info(pdf_text, filename=""):
    """Extract stock code and abbreviation from PDF text or filename.
    Returns (stock_code, stock_abbr) e.g. ("600080", "金花股份")
    """
    text = (pdf_text or "")[:12000]

    stock_code = None
    stock_abbr = None

    # Try content patterns
    code_match = re.search(r"(?:公司代码|证券代码|股票代码)[：:\s]*(\d{6})", text)
    if code_match:
        stock_code = code_match.group(1)

    abbr_match = re.search(
        r"(?:公司简称|证券简称|股票简称)[：:\s]*([^\s\n\d：:()（）]{2,20})",
        text,
    )
    if abbr_match:
        stock_abbr = abbr_match.group(1).strip()

    # Try filename for stock code
    if not stock_code:
        fname_match = re.search(r"(\d{6})", filename)
        if fname_match:
            stock_code = fname_match.group(1)

    # Try filename for stock abbr (Chinese name before colon)
    if not stock_abbr and filename:
        # Handle filenames like "华润三九：2023年年度报告.pdf"
        abbr_from_name = re.match(r"([^\d：:]+)[：:]", os.path.basename(filename))
        if abbr_from_name:
            stock_abbr = abbr_from_name.group(1).strip()

    return (stock_code, stock_abbr)


def calculate_yoy_growth(current, previous):
    """Calculate year-over-year growth rate.
    Formula: (current - previous) / |previous| * 100
    Returns None if either value is None or previous is 0.
    """
    if current is None or previous is None:
        return None
    if previous == 0:
        return None
    return round((current - previous) / abs(previous) * 100, 4)
