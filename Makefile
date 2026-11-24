.PHONY: install test run-pipeline run-api build-docker
install:
	python -m pip install -r requirements.txt

test:
	python -m pytest -q

run-pipeline:
	python -m src.pipeline --config config.yaml --demo

run-api:
	uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload

build-docker:
	docker compose build
