PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
IMAGE ?= claimlens:local
PORT ?= 8000
PLATFORM ?= linux/amd64
DOCKER ?= docker
RUN_DIR ?= output/evaluations/latency
CONFIG_VARS = BASE_URL API_KEY LLM_NAME LLM_BASE_URL LLM_API_KEY LLM_TIMEOUT_SECONDS LOCAL_MODEL_ID CONTEXT_TOKENS DOCUMENT_TIMEOUT_SECONDS MAX_DOCUMENT_MODEL_CALLS DOCUMENT_STRATEGY RETRIEVAL_PROMPT_TOKENS RETRIEVAL_TIMEOUT_SECONDS RETRIEVAL_QUERY_MODE RETRIEVAL_CITATION_MODE
FORWARD_ENV = $(foreach var,$(CONFIG_VARS),$(if $(filter undefined,$(origin $(var))),,-e $(var)))

.PHONY: run build submission dev test test-ui model-pull model-serve dataset booklets ocr-setup evaluate-prepare evaluate evaluate-score report verify-submission check-endpoint
build:
	$(DOCKER) build --platform $(PLATFORM) --target app -t $(IMAGE) .

submission:
	$(DOCKER) build --platform $(PLATFORM) --target submission -t claimlens:submission .

run: build
	mkdir -p data/local/library
	$(DOCKER) run --rm --init --platform $(PLATFORM) -p 127.0.0.1:$(PORT):8000 -v "$(CURDIR)/data/local/library:/library" $(if $(wildcard .env),--env-file .env,) $(FORWARD_ENV) $(IMAGE) serve --host 0.0.0.0 --port 8000

dev:
	PYTHONPATH=src $(PYTHON) -m claimlens serve --port $(PORT)

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

test-ui:
	node tests/frontend_smoke.cjs

model-pull:
	$(PYTHON) scripts/pull_local_model.py

model-serve:
	bash scripts/serve_local_model.sh

check-endpoint:
	$(PYTHON) scripts/check_endpoint.py

# Install requirements-dev.txt first. Existing snapshots are preserved.
dataset:
	$(PYTHON) scripts/prepare_dataset.py

booklets:
	$(PYTHON) scripts/import_booklets.py

ocr-setup:
	$(PYTHON) scripts/setup_ocr.py

evaluate-prepare:
	$(PYTHON) scripts/evaluate_fast.py prepare --directory "$(RUN_DIR)"

evaluate:
	$(PYTHON) scripts/evaluate_fast.py run --directory "$(RUN_DIR)"

evaluate-score:
	$(PYTHON) scripts/evaluate_fast.py score --directory "$(RUN_DIR)"

report:
	$(PYTHON) scripts/build_submission_report.py

verify-submission: submission
	$(DOCKER) run --rm --platform $(PLATFORM) --network none --read-only --tmpfs /tmp -v "$(CURDIR)/tests:/tests:ro" --entrypoint python claimlens:submission -m unittest discover -s /tests -p test_submission.py -v
