# pdfExtractor Module

**Generated:** 2026-04-18

## OVERVIEW

PDF → MySQL extraction pipeline. Task1 core module — parses financial report PDFs and inserts structured data into MySQL.

## STRUCTURE

```
pdfExtractor/
├── main.py            # CLI entry, process_pdf()
├── db_handler.py      # DBHandler class, SQL execution
├── pdf_parser.py      # PDFParser, text extraction
├── field_extractor.py # FieldExtractor, text → fields
├── utils.py           # Helpers
└── __init__.py       # Empty
```

## WHERE TO LOOK

| Symbol | Location | Role |
|--------|----------|------|
| DBHandler | `db_handler.py:27` | MySQL connection + upsert |
| PDFParser | `pdf_parser.py:12` | PDF → raw text |
| FieldExtractor | `field_extractor.py:14` | Parse fields from text |
| process_pdf | `main.py:30` | Main orchestration |

## CONVENTIONS

- **No new files here** — this is Task1, frozen
- Task2 must NOT modify this module
- If you need DB access in Task2, build new executor in `src/task2/`
- **Error type**: Use `DataValidationError` for validation failures

## ANTI-PATTERNS

- **NEVER** add Task2 logic here
- **NEVER** create new table definitions in multiple files
- **NEVER** use bare `except:` — use `DataValidationError`

## NOTES

- 6 Python files, depth 1
- MySQL schema: 4 core tables (income_sheet, balance_sheet, cash_flow_statement, index_table) — see db_handler.py:256-261
- CLI entry: `python -m pdfExtractor.main --config config.yaml --pdf-dir <dir>`