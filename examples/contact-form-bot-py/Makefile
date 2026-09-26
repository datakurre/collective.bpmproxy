.DEFAULT_GOAL := help

DEPLOY_FILES = ../contact-form/contact-form.bpmn ../contact-form/contact-form-start.form ../contact-form/contact-form-review.form ../contact-form/contact-form-delegated.form

.PHONY: help test deploy serve

help:
	@echo "make test|deploy|serve"

test:
	uv run --with="operaton-tasks[cli]" python -c "import tasks"

deploy:
	uv run --env-file secrets.env --with=purjo pur operaton deploy $(DEPLOY_FILES)

# Each example worker has its own default port, so more than one can run
# at a time (uvicorn's default, 8000, is now the review bot's alone).
PORT ?= 8001

serve:
	uv run --env-file secrets.env --with="operaton-tasks[cli]" operaton-tasks serve tasks.py -- --port $(PORT)
