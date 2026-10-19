# AI Strategy Map + WSJF Priority — command index.
# Scripts live in src/; data/config stay in the repo root. Run all targets
# from the repo root (make does this automatically).

PYTHON ?= python3

.DEFAULT_GOAL := help
.PHONY: help install build lock deploy test extract apply seed push pull clean

help:  ## Show this help
	@echo "AI Strategy Map + WSJF Priority — make targets:"
	@echo "  make install   Install Python deps + the headless Chromium browser"
	@echo "  make build     Rebuild the standalone HTML from the stories CSV"
	@echo "  make lock      Build the view-only locked bundle"
	@echo "  make deploy    Copy the regenerated HTML to app/index.html (run 'make build' first)"
	@echo "  make test      Run the full pytest suite"
	@echo "  make extract   Extract the editable app source -> src/strategy-map.src.html"
	@echo "  make apply     Apply src/strategy-map.src.html back into the bundle"
	@echo "  make seed      Seed initiatives.csv / settings.yaml / people.csv from the app"
	@echo "  make push      Create Jira issues for blank rows (needs .env)"
	@echo "  make pull      Refresh the stories CSV from linked Jira issues"
	@echo "  make clean     Remove generated build outputs"
	@echo ""
	@echo "Typical: make install && make build && make deploy"

install:  ## Install Python deps + Chromium
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) -m playwright install chromium

build:  ## Rebuild the standalone HTML from the stories CSV
	$(PYTHON) src/regenerate_html.py

lock:  ## Build the view-only locked bundle
	$(PYTHON) src/lock_app.py

deploy:  ## Copy the regenerated HTML to app/index.html
	@mkdir -p app
	@f=$$(ls *regenerated*.html 2>/dev/null | head -1); \
	if [ -z "$$f" ]; then \
	  echo "No *regenerated*.html found — run 'make build' first."; exit 1; \
	fi; \
	cp "$$f" app/index.html; \
	echo "deployed: $$f -> app/index.html"

test:  ## Run the full pytest suite
	$(PYTHON) -m pytest tests/ -q

extract:  ## Extract the editable app source
	$(PYTHON) src/apply_source.py --extract

apply:  ## Apply the editable app source back into the bundle
	$(PYTHON) src/apply_source.py

seed:  ## Seed the overlay files from the app's current content
	$(PYTHON) src/export_tabs.py

push:  ## Create Jira issues for blank CSV rows
	$(PYTHON) src/jira_sync.py push

pull:  ## Refresh the stories CSV from linked Jira issues
	$(PYTHON) src/jira_sync.py pull

clean:  ## Remove generated build outputs
	rm -f "Insignia AI Strategy Map - regenerated.html" \
	      "Insignia AI Strategy Map - locked.html" \
	      robust-locked.html divisions.csv divisions-current.csv \
	      *.load-error.png *.save-error.png *.tab-error.png
	rm -rf __pycache__ src/__pycache__ tests/__pycache__ .pytest_cache
	@echo "cleaned generated outputs (app/index.html and the CSV/HTML sources are kept)"
