# Personal Finance App

Local web application for processing and analyzing Mexican bank statements (Nu, BBVA, Banamex, Mercado Pago). Runs entirely offline — financial data never leaves your machine.

## Requirements

- [uv](https://docs.astral.sh/uv/getting-started/installation/) — Python package manager
- Python 3.14 (managed automatically by uv)

## Installation

```bash
# Clone and enter the project
git clone <repo-url>
cd personal-finance-app

# Install dependencies
uv sync
```

## Database setup

```bash
# Create the SQLite database and apply all migrations
uv run alembic upgrade head
```

The database is created at `data/finance.db`.

## Running the app

```bash
uv run streamlit run src/finances/app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

## Development commands

```bash
# Lint and format
uv run ruff check src/
uv run ruff format src/

# Generate a new migration after model changes
uv run alembic revision --autogenerate -m "description"

# Apply pending migrations
uv run alembic upgrade head

# Rollback one migration
uv run alembic downgrade -1

# Commit with conventional commits (interactive)
uv run cz commit

# Bump version and generate CHANGELOG
uv run cz bump
```

## Project structure

```
src/finances/
  app.py              # Streamlit entry point
  core/               # Database engine and settings
  models/             # SQLAlchemy ORM models
  parsers/            # PDF parsers — one per bank/account type
  repositories/       # Database query layer
  services/           # Business logic
  views/              # Streamlit pages
data/                 # SQLite DB and archived PDFs (git-ignored)
migrations/           # Alembic migration files
```
