# Next Core — canonical developer commands (referenced by CLAUDE.md; do not invent alternatives)

.PHONY: install lint format typecheck test test-unit test-integration check docs run \
        test-db-start test-db-stop clean

UV ?= uv
TEST_DB_DIR ?= $(CURDIR)/.pgdev
TEST_DB_PORT ?= 5433
export TEST_DB_PORT

install:
	$(UV) sync

lint:
	$(UV) run ruff check src tests
	$(UV) run ruff format --check src tests

format:
	$(UV) run ruff format src tests
	$(UV) run ruff check --fix src tests

typecheck:
	$(UV) run mypy src tests

test-unit:
	$(UV) run coverage run -m pytest tests/unit -x
	$(UV) run coverage report

test-integration:
	$(UV) run pytest tests/integration -x

test:
	$(UV) run coverage run -m pytest tests
	$(UV) run coverage report

check: lint typecheck test docs
	@echo "make check: ALL GATES PASSED"

docs:
	$(UV) run mkdocs build --strict

run:
	$(UV) run python manage.py runserver 0.0.0.0:8000

# --- Local real-PostgreSQL for tests when Docker is unavailable (see STATUS.md) -----------
# Uses system PostgreSQL 16 binaries; data dir is git-ignored.

PG_BIN := $(shell ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -1)
# PostgreSQL refuses to run as root: in root containers, run it as the unprivileged
# `postgres` user (present via the postgresql system package).
PG_RUN := $(shell [ "$$(id -u)" = "0" ] && echo "setpriv --reuid=postgres --regid=postgres --clear-groups" || echo "")

test-db-start:
	@mkdir -p $(TEST_DB_DIR) && { [ -z "$(PG_RUN)" ] || chown postgres:postgres $(TEST_DB_DIR); }
	@test -f $(TEST_DB_DIR)/PG_VERSION || $(PG_RUN) $(PG_BIN)/initdb -D $(TEST_DB_DIR) -U nextcore -A trust >/dev/null
	@$(PG_RUN) $(PG_BIN)/pg_ctl -D $(TEST_DB_DIR) -o "-p $(TEST_DB_PORT) -k /tmp" -l $(TEST_DB_DIR)/log start
	@for db in next_core_dev next_core_ta next_core_tb; do \
		$(PG_RUN) $(PG_BIN)/createdb -h 127.0.0.1 -p $(TEST_DB_PORT) -U nextcore $$db 2>/dev/null || true; \
	done
	@echo "PostgreSQL ready on port $(TEST_DB_PORT) (dbs: next_core_dev + tenant test dbs, user: nextcore)"

test-db-stop:
	@$(PG_RUN) $(PG_BIN)/pg_ctl -D $(TEST_DB_DIR) stop >/dev/null 2>&1 || true

clean: test-db-stop
	rm -rf $(TEST_DB_DIR) .coverage site .mypy_cache .pytest_cache .ruff_cache
