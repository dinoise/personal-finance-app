# Agent Guide — Personal Finance App

## Project Overview

Local web application (Streamlit) for processing, visualizing, and analyzing Mexican bank statements.
Runs entirely on Linux with no cloud dependencies. Financial data never leaves the user's machine.

**Owner:** Luis Hector Aguilar Valenzuela
**Stack:** Python 3.14 · uv · Streamlit · SQLite + SQLAlchemy 2.0 + Alembic · pdfplumber · PyMuPDF · Plotly · Prophet

## Project Structure

```
src/finances/
  __init__.py          # __version__ lives here
  app.py               # Streamlit entry point: uv run streamlit run src/finances/app.py
  core/
    config.py          # Settings (pydantic-settings), singleton `settings`
    database.py        # SQLAlchemy engine, Base, get_db(), SQLite PRAGMAs
  models/              # SQLAlchemy ORM — 1:1 with DB tables
  parsers/             # Factory pattern — one parser per bank/account type
  services/            # Business logic, no UI dependency
  analytics/           # pandas/scipy statistics and Prophet forecasting
  views/               # Streamlit pages (UI only)
  config/              # User-editable JSON: categories.json, labels.json, budgets.json
migrations/            # Alembic — render_as_batch=True required for SQLite
tests/
  parsers/             # Integration tests with real PDFs as fixtures
  services/
data/                  # SQLite DB and PDFs — never committed (see .gitignore)
```

## Common Commands

```bash
uv run streamlit run src/finances/app.py   # run the app
uv run pytest                              # run tests
uv run alembic upgrade head                # apply migrations
uv run alembic revision --autogenerate -m "description"  # generate migration
uv run cz commit                           # interactive conventional commit
uv run cz bump                             # bump version + generate CHANGELOG
```

## Versioning

Commitizen manages versioning. On `cz bump`:
- `pyproject.toml` → `[project].version`
- `src/finances/__init__.py` → `__version__`
- `CHANGELOG.md` updated incrementally

Version follows SemVer. Tag format: `v1.2.3`.

## Commit Convention

All commits must follow Conventional Commits. The `commit-msg` pre-commit hook enforces this.

| Type | When to use | SemVer impact |
|---|---|---|
| `fix` | A bug fix | PATCH |
| `feat` | A new feature | MINOR |
| `docs` | Documentation only changes | none |
| `style` | Formatting, whitespace — no logic change | none |
| `refactor` | Code change that neither fixes a bug nor adds a feature | none |
| `perf` | A code change that improves performance | none |
| `test` | Adding or correcting tests | none |
| `build` | Build system or external dependencies (pip, docker) | none |
| `ci` | CI configuration files and scripts | none |
| `chore` | Maintenance tasks that don't modify src or test files | none |

**Breaking changes:** append `!` after the type (`feat!:`) or add `BREAKING CHANGE:` in the footer → MAJOR bump.

**Format:**
```
type(optional-scope): short description

optional body

optional footer
```

**Examples:**
```
feat(parsers): add MercadoPago PDF parser
fix(database): correct WAL pragma for concurrent Streamlit access
build(deps): add pdfplumber and PyMuPDF
chore: update pre-commit hooks
```

## Critical Domain Rules

- **Internal transfer detection:** always compare `to_clabe` against `accounts.clabe` — never by name.
  The account holder's name appears in every SPEI transfer by BANXICO regulation.
- **BBVA CLABE:** strip the `00` prefix from the 20-digit raw number → `raw[-18:]`.
- **CLABE is the unique account identifier**, not the (bank, account_type) pair — Nu has two accounts at the same bank.
- **SQLite PRAGMAs** `foreign_keys = ON` and `journal_mode = WAL` must always be set on engine connect.
- **Alembic** requires `render_as_batch=True` in `migrations/env.py` for all ALTER TABLE operations on SQLite.
