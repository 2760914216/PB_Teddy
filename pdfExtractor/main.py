import argparse
import json
import logging
import os
import sys

from pdfExtractor.db_handler import DBHandler, DataValidationError
from pdfExtractor.field_extractor import FieldExtractor
from pdfExtractor.pdf_parser import PDFParser

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def _error_entry(pdf_path, stage, reason, **details):
    payload = {
        "pdf": os.path.basename(pdf_path),
        "failure_stage": stage,
        "reason": reason,
    }
    if details:
        payload["details"] = details
    return payload


def process_pdf(pdf_path, db, error_log):
    fname = os.path.basename(pdf_path)
    logger.info(f"Processing: {fname}")

    try:
        parser = PDFParser(pdf_path)
    except Exception as exc:
        msg = f"Failed to open PDF: {fname}"
        logger.exception(msg)
        error_log.append(
            _error_entry(pdf_path, "pdf_open", exc.__class__.__name__, message=str(exc))
        )
        return False

    try:
        extractor = FieldExtractor(parser)
        if not extractor.stock_code or not extractor.report_period:
            error_log.append(
                _error_entry(
                    pdf_path,
                    "metadata",
                    "missing_identity",
                    diagnostics=extractor.diagnostics,
                )
            )
            return False

        logger.info(
            f"  Stock: {extractor.stock_code} ({extractor.stock_abbr}), "
            f"Period: {extractor.report_period}"
        )

        income = extractor.extract_income_sheet()
        balance = extractor.extract_balance_sheet()
        cashflow = extractor.extract_cash_flow_sheet()
        core = extractor.extract_core_indicators()

        statements = {
            "income_sheet": income,
            "balance_sheet": balance,
            "cash_flow_sheet": cashflow,
            "core_performance_indicators_sheet": core,
        }
        missing = [name for name, payload in statements.items() if not payload]
        if missing:
            error_log.append(
                _error_entry(
                    pdf_path,
                    "field_extraction",
                    "missing_statement_output",
                    missing=missing,
                    diagnostics=extractor.diagnostics,
                )
            )
            return False

        assert income is not None
        assert balance is not None
        assert cashflow is not None
        assert core is not None

        db.begin()
        try:
            db.insert_income_sheet(income, commit=False)
            logger.info(
                f"  income_sheet: OK (revenue={income.get('total_operating_revenue')})"
            )
            db.insert_balance_sheet(balance, commit=False)
            logger.info(
                f"  balance_sheet: OK (assets={balance.get('asset_total_assets')})"
            )
            db.insert_cash_flow_sheet(cashflow, commit=False)
            logger.info(
                f"  cash_flow_sheet: OK (net_cf={cashflow.get('net_cash_flow')})"
            )
            db.insert_core_indicators(core, commit=False)
            logger.info(f"  core_indicators: OK (eps={core.get('eps')})")
            db.commit()
        except DataValidationError as exc:
            db.rollback()
            error_log.append(
                _error_entry(
                    pdf_path,
                    "preinsert_validation",
                    exc.reason,
                    table=exc.table,
                    field=exc.field,
                    value=exc.value,
                )
            )
            return False
        except Exception as exc:
            db.rollback()
            logger.exception("Database write failed for %s", fname)
            error_log.append(
                _error_entry(
                    pdf_path,
                    "db_write",
                    exc.__class__.__name__,
                    message=str(exc),
                )
            )
            return False

        return True
    except Exception as exc:
        msg = f"Error processing {fname}"
        logger.exception(msg)
        error_log.append(
            _error_entry(
                pdf_path,
                "unexpected",
                exc.__class__.__name__,
                message=str(exc),
            )
        )
        return False
    finally:
        parser.close()


def main():
    arg_parser = argparse.ArgumentParser(
        description="Extract financial data from PDF reports"
    )
    arg_parser.add_argument(
        "pdf_dir",
        nargs="?",
        default=".",
        help="Directory containing PDF files (default: .)",
    )
    arg_parser.add_argument(
        "--output-dir",
        default="ex_db_result",
        help="Output directory for CSV and logs (default: ex_db_result)",
    )
    arg_parser.add_argument(
        "--config",
        default="config.yaml",
        help="Config file path (default: config.yaml)",
    )
    args = arg_parser.parse_args()

    pdf_dir = args.pdf_dir
    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)

    log_file = os.path.join(output_dir, "extraction.log")
    file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logging.getLogger().addHandler(file_handler)

    pdf_files = sorted(
        [
            os.path.join(pdf_dir, f)
            for f in os.listdir(pdf_dir)
            if f.lower().endswith(".pdf")
        ]
    )

    if not pdf_files:
        logger.error(f"No PDF files found in {pdf_dir}")
        sys.exit(1)

    logger.info(f"Found {len(pdf_files)} PDF files in {pdf_dir}")

    db = DBHandler(config_path=args.config)
    db.connect()
    logger.info("Connected to MySQL database")

    error_log = []
    success_count = 0

    try:
        for pdf_path in pdf_files:
            if process_pdf(pdf_path, db, error_log):
                success_count += 1

        logger.info(f"\nProcessed {success_count}/{len(pdf_files)} PDFs successfully")

        if error_log:
            logger.warning(f"Errors ({len(error_log)}):")
            for err in error_log:
                logger.warning("  - %s", json.dumps(err, ensure_ascii=False))

        logger.info(f"Exporting CSV to {output_dir}")
        db.export_all_tables(output_dir)
        logger.info("CSV export complete")
    finally:
        db.close()

    error_log_path = os.path.join(output_dir, "errors.log")
    with open(error_log_path, "w", encoding="utf-8") as f:
        if error_log:
            for err in error_log:
                f.write(json.dumps(err, ensure_ascii=False) + "\n")
        else:
            f.write("No errors\n")

    logger.info(f"Error log written to {error_log_path}")
    logger.info("Done!")


if __name__ == "__main__":
    main()
