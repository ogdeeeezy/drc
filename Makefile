.PHONY: install dev test lint run clean frontend frontend-build

PYTHON := python3.12
VENV := .venv
BIN := $(VENV)/bin

install:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -e .

dev:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -e ".[dev]"

test:
	$(BIN)/pytest tests/unit/ -v

test-all:
	$(BIN)/pytest tests/ -v

lint:
	$(BIN)/ruff check backend/ tests/
	$(BIN)/ruff format --check backend/ tests/

format:
	$(BIN)/ruff check --fix backend/ tests/
	$(BIN)/ruff format backend/ tests/

run:
	$(BIN)/uvicorn backend.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

frontend-install:
	cd frontend && npm install

clean:
	rm -rf $(VENV) *.egg-info dist build __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
