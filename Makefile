.PHONY: playground install run run-fake test lint mock openapi keys
install:
	python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
run:
	uvicorn app.main:create_app --factory --reload --reload-dir app --reload-dir prompts --port 8000
run-fake:
	FAKE_MODELS=true AUTH_DISABLED=true uvicorn app.main:create_app --factory --reload --reload-dir app --reload-dir prompts --port 8000
mock:
	uvicorn mock.mock_server:app --reload --port 8001
test:
	pytest -q
lint:
	ruff check . && ruff format --check .
openapi:
	python -m scripts.export_openapi
keys:
	python scripts/gen_dev_keys.py
playground:
	PYTHONPATH=. streamlit run playground/streamlit_app.py
