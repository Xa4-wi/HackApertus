PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
IMAGE ?= claimlens:local
PORT ?= 8000
PLATFORM ?= linux/amd64
CONFIG_VARS = BASE_URL API_KEY LLM_NAME LLM_BASE_URL LLM_API_KEY LLM_TIMEOUT_SECONDS LOCAL_MODEL_ID
FORWARD_ENV = $(foreach var,$(CONFIG_VARS),$(if $(filter undefined,$(origin $(var))),,-e $(var)))

.PHONY: run build submission dev test demo model-pull model-serve dataset
build:
	docker build --platform $(PLATFORM) --target demo -t $(IMAGE) .

submission:
	docker build --platform $(PLATFORM) --target submission -t claimlens:submission .

run: build
	docker run --rm --init --platform $(PLATFORM) -p 127.0.0.1:$(PORT):8000 $(if $(wildcard .env),--env-file .env,) $(FORWARD_ENV) $(IMAGE) serve --host 0.0.0.0 --port 8000

dev:
	PYTHONPATH=src $(PYTHON) -m claimlens serve --port $(PORT)

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

demo:
	PYTHONPATH=src $(PYTHON) -m claimlens --input data/demo-cases.jsonl --output output/demo-predictions.jsonl --demo

model-pull:
	$(PYTHON) scripts/pull_local_model.py

model-serve:
	bash scripts/serve_local_model.sh

# Install requirements-data.txt first. Existing snapshots are preserved.
dataset:
	$(PYTHON) scripts/prepare_dataset.py
