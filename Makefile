PYTHON ?= $(shell \
	if [ -x .venv/bin/python ]; then \
		printf '%s' .venv/bin/python; \
	elif command -v python3.11 >/dev/null 2>&1; then \
		printf '%s' python3.11; \
	else \
		printf '%s' python3; \
	fi)
PIP ?= .venv/bin/pip
UVICORN ?= .venv/bin/uvicorn
UV_CACHE_DIR ?= .uv-cache
export PYTHONPATH := $(CURDIR)/src:$(CURDIR)

.PHONY: setup verify review verify-e2e metrics recommendation price-backtest price-backtest-reference experiments ai-advisor-audit advisor-run-audit advisor-budget collect-advisor-runs advisor-experiment review-dashboard verify-data privacy-audit figure-audit repro-docker configure-env api ui app run paper all submission package clean

setup:
	if command -v uv >/dev/null 2>&1; then \
		UV_CACHE_DIR=$(UV_CACHE_DIR) uv sync --frozen --extra dev; \
	else \
		python3.11 -m venv .venv; \
		.venv/bin/python -m ensurepip --upgrade; \
		.venv/bin/python -m pip install -e ".[dev]"; \
	fi
	cd frontend && npm ci

verify:
	bash scripts/verify.sh

# One command for a reviewer: re-derive the paper's headline numbers from the
# frozen data, confirm data integrity, and confirm no private data leaks.
review:
	@$(PYTHON) scripts/hash_data.py
	@$(PYTHON) scripts/reviewer_check.py
	@$(PYTHON) scripts/check_artifact_privacy.py
	@echo "Open paper/data/review_dashboard.html for the per-model audit dashboard."

verify-e2e:
	cd frontend && npm run test:e2e

metrics:
	$(PYTHON) scripts/reviewer_metrics.py

recommendation:
	$(PYTHON) scripts/moat_compounding_analysis.py --cash 1500.00

price-backtest:
	$(PYTHON) scripts/price_backtest.py --start 2021-01-01 --benchmark SPY

price-backtest-reference:
	$(PYTHON) scripts/price_backtest.py --holdings tests/fixtures/seed_portfolio_broker.csv --return-matrix paper/data/returns_matrix.csv --reference-output paper/data/price_backtest_reference.json --generated-utc 20260604_170710

experiments:
	$(PYTHON) scripts/run_experiments.py

ai-advisor-audit:
	$(PYTHON) scripts/run_ai_advisor_audit.py --reference

advisor-run-audit:
	$(PYTHON) scripts/collect_advisor_runs.py --provider azure --model chat --runs 3 --cache-root paper/data/advisor_runs --out-dir exports/advisor_run_audit/azure_chat_policy

advisor-budget:
	$(PYTHON) scripts/estimate_advisor_budget.py --runs 3

collect-advisor-runs:
	$(PYTHON) scripts/collect_advisor_runs.py --runs 3

advisor-experiment:
	$(PYTHON) scripts/run_advisor_experiment.py

review-dashboard:
	$(PYTHON) scripts/build_review_dashboard.py

verify-data:
	$(PYTHON) scripts/hash_data.py

privacy-audit:
	$(PYTHON) scripts/check_artifact_privacy.py

figure-audit:
	bash scripts/check_figure_vectors.sh

repro-docker:
	docker build -f Dockerfile.repro -t actionaudit-repro .
	docker run --rm actionaudit-repro

configure-env:
	bash scripts/configure_env.sh

api:
	$(UVICORN) arenawealth.api.main:app --host 127.0.0.1 --port 8000 --reload

ui:
	cd frontend && npm run dev -- --host 127.0.0.1

app:
	bash scripts/start.sh

run:
	bash scripts/start.sh

paper:
	cd paper && latexmk -pdf main.tex

all: setup review verify price-backtest-reference experiments ai-advisor-audit advisor-run-audit verify-data figure-audit
	@echo "Artifact reproduced end-to-end: tests, data, cached runs, and figures are up to date."

submission: all paper
	@echo "Submission reproduced end-to-end: artifact plus local paper build are up to date."

package:
	bash scripts/package_artifact.sh

clean:
	rm -rf .pytest_cache .ruff_cache frontend/dist frontend/test-results frontend/playwright-report exports logs
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
