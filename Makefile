.PHONY: test lint data-check experiment loss readme

test:
	python3 -m unittest discover -s tests

lint:
	ruff check . && ruff format --check .

data-check:
	python3 tools/fetch_data.py --verify

experiment:
	python3 experiment.py --out results/metrics.json

loss:
	python3 -m capturedrift.loss --out results/metrics-v2.json

readme:
	python3 demo.py --readme README.md --out README.md
	python3 demo_loss.py
