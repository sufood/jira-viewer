# AI Strategy Map + WSJF Priority — command index.
# Scripts live in src/; data/config stay in the repo root. Run all targets
# from the repo root (make does this automatically).

PYTHON ?= python3

.DEFAULT_GOAL := help
.PHONY: help install build bundle engine-extract lock deploy test seed push pull import clean apply extract

help:  ## Show this help
	@echo "AI Strategy Map + WSJF Priority — make targets:"
	@echo "  make install   Install Python deps + the headless Chromium browser"
	@echo "  make build     Assemble the app bundle from source, THEN render the HTML"
	@echo "                 (override CSV=… OUT=… HTML=…)"
	@echo "  make bundle    (Re)assemble the app bundle from src/ only (no render)"
	@echo "  make lock      Build the view-only locked bundle"
	@echo "  make deploy    Copy the regenerated HTML to app/index.html (run 'make build' first)"
	@echo "  make test      Run the full pytest suite"
	@echo "  make seed      Seed initiatives.csv / settings.yaml / people.csv from the app"
	@echo "  make push      Create Jira issues for blank rows (needs .env)"
	@echo "  make pull      Refresh the stories CSV from linked Jira issues"
	@echo "  make import    Read all issues in a project/JQL into a CSV (needs .env)"
	@echo "  make clean     Remove generated build outputs (incl. the assembled bundle)"
	@echo ""
	@echo "  Maintenance: make engine-extract  (re-vendor runtime/fonts when the engine changes)"
	@echo ""
	@echo "Edit the app: edit src/strategy-map.src.html, then 'make build'. No 'apply' step."
	@echo "Typical:      make install && make build && make deploy"

install:  ## Install Python deps + Chromium (+ truststore for corporate TLS proxies)
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) -m pip install truststore
	$(PYTHON) -m playwright install chromium

# The app bundle is a GENERATED artifact, assembled from source each build:
#   src/engine/                  vendored runtime + fonts + manifest skeleton
#   src/strategy-map.src.html    the ONLY editable app source
# build_bundle.py folds in what used to be a separate `apply`, so there is no
# stale-bundle footgun. Override the dataset with:
#   make build CSV=ai-topics.csv OUT="AI Topics.html"
build:  ## Assemble the bundle from source, then render the HTML (override CSV=… OUT=… HTML=…)
	$(PYTHON) src/build_bundle.py
	$(PYTHON) src/regenerate_html.py $(if $(CSV),--csv "$(CSV)",) $(if $(OUT),--out "$(OUT)",) $(if $(HTML),--html "$(HTML)",)

bundle:  ## (Re)assemble the app bundle from src/engine + src/strategy-map.src.html (no render)
	$(PYTHON) src/build_bundle.py

# Maintenance only: re-derive src/engine/ (vendored runtime + fonts + skeleton)
# from an existing bundle. Run when the upstream engine changes, not for app edits.
engine-extract:  ## Re-vendor the engine from an existing bundle (maintenance)
	$(PYTHON) src/decompose_bundle.py

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

seed:  ## Seed the overlay files from the app's current content
	$(PYTHON) src/export_tabs.py

# push creates issues in Jira and pull can overwrite existing CSV values; both
# prompt for a y/N (default N) first. Pass YES=1 to skip the prompt (unattended).
push:  ## Create Jira issues for blank CSV rows (prompts first; YES=1 to skip)
	$(PYTHON) src/jira_sync.py push $(if $(YES),--yes,)

pull:  ## Refresh the stories CSV from linked Jira issues (prompts before overwriting; YES=1 to skip)
	$(PYTHON) src/jira_sync.py pull $(if $(YES),--yes,)

import:  ## Read all issues in a project/JQL into a CSV (set CSV=… PROJECT=… BOARD=…)
	$(PYTHON) src/jira_sync.py import $(if $(PROJECT),--project "$(PROJECT)",) $(if $(CSV),--csv "$(CSV)",) $(if $(BOARD),--board "$(BOARD)",)

# Low-level maintenance (rarely needed now that `build` assembles from source):
#   apply   — patch src/strategy-map.src.html into an existing bundle in place
#   extract — pull the app source out of a bundle back into src/strategy-map.src.html
apply:
	$(PYTHON) src/apply_source.py
extract:
	$(PYTHON) src/apply_source.py --extract

clean:  ## Remove generated build outputs (incl. the assembled bundle)
	@if [ -f src/engine/skeleton.html ]; then \
	  rm -f "Insignia AI Strategy Map - Jira linked.html"; \
	  echo "removed the assembled bundle (rebuild with 'make build' / 'make bundle')"; \
	else \
	  echo "kept the bundle: src/engine/ not found, so it can't be reassembled yet"; \
	fi
	rm -f "Insignia AI Strategy Map - regenerated.html" \
	      "Insignia AI Strategy Map - locked.html" \
	      robust-locked.html divisions.csv divisions-current.csv \
	      *.load-error.png *.save-error.png *.tab-error.png
	rm -rf __pycache__ src/__pycache__ tests/__pycache__ .pytest_cache
	@echo "cleaned generated outputs (CSV/HTML sources are kept)"
