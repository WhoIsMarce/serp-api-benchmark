.PHONY: install test lint mock-server mock-run check run report trend clean

PY ?= python

install:
	$(PY) -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"

test:
	pytest -q

lint:
	ruff check src tests

# Terminal 1: make mock-server     Terminal 2: make mock-run
mock-server:
	serpbench mock-server --port 8765 --speed 0.05

mock-run:
	serpbench run --config config/providers.mock.yaml --repeats 3 --limit 12 \
		--vantage-point local-synthetic -y

check:
	serpbench check

# Real run. Spends paid credits. Set VANTAGE to where you are running from.
VANTAGE ?= unspecified
run:
	serpbench run --repeats 5 --vantage-point $(VANTAGE)

# usage: make report RUN=20261006T120000Z
report:
	serpbench report --run $(RUN)

trend:
	serpbench trend

clean:
	rm -rf .pytest_cache .ruff_cache build dist *.egg-info results/*-synthetic