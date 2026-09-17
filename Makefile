.PHONY: install dev lint fmt typecheck test run clean

PYTHON := python
PIP    := pip
APP    := careerpilot

# ── Setup ─────────────────────────────────────────────────────────────────────
install:
	$(PIP) install -e .

dev:
	$(PIP) install -e ".[dev]"

# ── Quality ───────────────────────────────────────────────────────────────────
lint:
	ruff check .

fmt:
	ruff format .

typecheck:
	mypy .

# ── Tests ─────────────────────────────────────────────────────────────────────
test:
	pytest -v

test-cov:
	pytest -v --cov=. --cov-report=html
	@echo "Coverage report at htmlcov/index.html"

# ── Run ───────────────────────────────────────────────────────────────────────
run:
	$(PYTHON) -m orchestration.pipeline

cli:
	$(APP) --help

# ── Database ──────────────────────────────────────────────────────────────────
db-init:
	alembic upgrade head

db-migrate:
	alembic revision --autogenerate -m "$(msg)"

# ── Clean ─────────────────────────────────────────────────────────────────────
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null; true
	find . -name "*.pyc" -delete 2>/dev/null; true
	@echo "Cleaned."
