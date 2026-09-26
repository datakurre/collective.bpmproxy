.DEFAULT_GOAL := help

.PHONY: help test serve

help:
	@echo "make test|serve"

test:
	uv run --with="operaton-tasks[cli]" python -c "import tasks"

# Each example worker has its own default port, so more than one can run
# at a time (uvicorn's default, 8000, is now the review bot's alone).
PORT ?= 8000

serve:
	uv run --env-file secrets.env --with="operaton-tasks[cli]" operaton-tasks serve tasks.py -- --port $(PORT)
