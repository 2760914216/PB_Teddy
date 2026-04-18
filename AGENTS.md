# PROJECT KNOWLEDGE BASE

**Generated:** 2026-04-18
**Commit:** 25b6759
**Branch:** (single branch, no remote)

## OVERVIEW

CLI for financial report Q&A over MySQL with Ollama LLM. Project targets Task2 of B_problem.pdf — build a Chinese interactive CLI that understands natural language questions, generates safe SQL, queries financial data, and optionally produces charts. Output is Excel + JSON per 附件7.

## STRUCTURE

```
PB_THE/
├── config.yaml              # Single config entry (DB + paths)
├── Teddy-spec.md           # Mandatory conventions
├── Teddy-task2.md          # Task2 requirements
├── pdfExtractor/           # Task1: PDF parsing → MySQL (23 py files total)
│   ├── main.py             # CLI entry, argparse + logging
│   ├── db_handler.py       # MySQL read/write, query()
│   ├── pdf_parser.py       # PDF text extraction
│   ├── field_extractor.py # Field extraction from parsed PDF
│   └── utils.py
├── test/                   # check_*.py regression scripts
├── scripts/                # Helper scripts
├── financial_report_set/   # Input PDFs (36 files)
├── 示例数据/                # Sample data
└── result/                 # Output dir (to be created by task2)
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Config | `config.yaml` | DB connection only; task2 needs extension |
| DB access | `pdfExtractor/db_handler.py:54-91` | PyMySQL, DictCursor |
| CLI pattern | `pdfExtractor/main.py:151-175` | argparse+logging reference |
| MySQL schema | `pdfExtractor/db_handler.py:256-261` | 4 core tables: income_sheet, etc |
| Task2 spec | `Teddy-spec.md`, `Teddy-task2.md` | Requirements + acceptance |

## CODE MAP

| Symbol | Type | Location | Refs | Role |
|--------|------|----------|------|------|
| DBHandler | class | `db_handler.py:27` | 2 | MySQL CRUD |
| PDFParser | class | `pdf_parser.py:12` | 1 | PDF → text |
| FieldExtractor | class | `field_extractor.py:14` | 1 | Text → fields |
| process_pdf | func | `main.py:30` | 0 | Entry orchestration |
| DataValidationError | class | `db_handler.py:23` | 2 | Error type |

## CONVENTIONS (THIS PROJECT)

- **Python env**: `~/.venv` + `uv` package manager (mandatory per Teddy-spec.md)
- **Config**: Single `config.yaml` — extend, never create separate file
- **Output dir**: `result/` per Teddy-spec.md:21-23 (numbered format: `result_1.xlsx`, `{n}_{m}.jpg`)
- **Error handling**: Use `DataValidationError` from db_handler, not bare exceptions
- **Test**: No pytest; use `test/check_*.py` scripts for regression

## ANTI-PATTERNS (THIS PROJECT)

- **NEVER** create `task2.yaml` or `.env` — extend `config.yaml`
- **NEVER** hardcode table names in multiple modules — centralize in db_handler.py
- **NEVER** put business logic in `main.py` — keep entry thin, modules thick
- **NEVER** use absolute paths — all paths relative to work_dir or from config

## UNIQUE STYLES

- **No GUI/TUI frameworks** — pure CLI per Teddy-spec.md
- **No LangChain/CrewAI/vector/RAG** — only Ollama direct calls
- **No automated test framework** — use script-based validation
- **Chinese-first** — all user-facing output in Chinese

## COMMANDS

```bash
# Current project (Task1)
python -m pdfExtractor.main --config config.yaml --pdf-dir pdf提取测试集

# Future (Task2)
python -m src.task2.cli --config config.yaml  # after implementation
```

## NOTES

- Project has **23 Python files**, depth 3 max, small enough for flat structure
- `src/task2/` directory **does not exist yet** — task2 is planned but not created
- MySQL schema uses 4 core financial tables (income_sheet, etc.) — confirmed in db_handler.py:256-261
- No existing AGENTS.md or CLAUDE.md in project