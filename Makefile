.PHONY: help test fixture run demo citations validate verify clean

SERVICE_NAME ?= eeg-report
PYTHON ?= .venv/bin/python
DEMO ?= siena

.DEFAULT: help

help:
	@echo "Make Help for $(SERVICE_NAME)"
	@echo ""
	@echo "make test       - pytest on the synthetic fixture (no Docker; the PDF test needs Pango, else skipped)"
	@echo "make fixture    - write the synthetic fixture to data/fixture/{linked,flat}/"
	@echo "make run        - build the image and run it (read-only, uid 65534, no network) over data/fixture/linked/ (or INPUT_HOST=...) into data/output/"
	@echo "make demo       - the image on a demo's real step outputs (DEMO=siena|chbmit|ds003555) into ../workflow-scalp-eeg/data/work/DEMO/eeg-report/"
	@echo "make citations  - rebuild processor/references.json from the sibling apps' CITATION.cff files and the registries"
	@echo "make validate   - app.yml against the manifest schema, CITATION.cff with cffconvert"
	@echo "make verify     - every citation of CITATION.cff and README.md against Crossref/DataCite/PubMed"
	@echo "make clean      - remove data/output/"
	@echo ""
	@echo "PYTHON=$(PYTHON) (python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt)"

test:
	$(PYTHON) -m pytest -q tests

fixture:
	$(PYTHON) -m tests.make_fixture data/fixture --layout both

run: clean fixture
	mkdir -p data/output
	docker compose -f docker-compose.yml down --remove-orphans
	docker compose -f docker-compose.yml build
	docker compose -f docker-compose.yml up --exit-code-from processor
	docker compose -f docker-compose.yml down --remove-orphans
	@echo "--- outputs:"
	@find data/output -type f | sort | head -50

demo:
	docker build --platform linux/amd64 -t eeg-report:dev .
	scripts/run_demo.sh $(DEMO)

citations:
	$(PYTHON) scripts/build_citations.py

validate:
	$(PYTHON) scripts/validate.py

verify:
	$(PYTHON) ../workflow-scalp-eeg/scripts/verify-citations.py .

clean:
	rm -rf data/output
