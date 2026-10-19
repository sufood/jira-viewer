# AI Strategy Map + WSJF Priority — Jira ⇄ CSV ⇄ Standalone-HTML Toolkit

A self-contained, single-file HTML app that visualises a portfolio of opportunities as an
interactive **strategy map** and a **WSJF prioritisation studio**, driven entirely by one CSV.
A small Python toolkit keeps that CSV in sync with Jira (create issues, pull updates) and
rebuilds the shippable HTML from the CSV.

- **Strategy map** — divisions fan out around a hub; click a division to see its opportunities,
  people, gaps and next steps.
- **Priority tab** — a full **WSJF (Weighted Shortest Job First)** studio: an executive Top‑10,
  an editable scoring grid, a value/effort matrix, bubble/heatmap/sprint‑staircase views, and
  live "what‑if" weighting — all scored automatically from the story text.
- **One shared store** — the map and every Priority view read the *same* stories, so a
  division's cards fan out in WSJF order, and a "priority heat" overlay tints the map by WSJF.

The shipped artifact is a **single `.html` file** with everything embedded (JS, fonts, data).
It needs no server and works offline, including from a `file://` path.

---

## Table of contents

1. [How it fits together](#how-it-fits-together)
2. [Prerequisites & install](#prerequisites--install)
3. [Quick start (provided data)](#quick-start-provided-data)
4. [Using `make`](#using-make)
5. [The stories CSV — the single source of truth](#the-stories-csv--the-single-source-of-truth)
6. [Jira Sync — `push` and `pull`](#jira-sync--push-and-pull)
7. [Regenerate & lock the app](#regenerate--lock-the-app)
8. [Fresh setup from a *different* Jira & project](#fresh-setup-from-a-different-jira--project)
9. [Editing the app itself (WSJF Priority tab & UI)](#editing-the-app-itself-wsjf-priority-tab--ui)
10. [The WSJF Priority tab in depth](#the-wsjf-priority-tab-in-depth)
11. [File reference](#file-reference)
12. [Tests](#tests)
13. [Troubleshooting](#troubleshooting)

---

## How it fits together

```
                    push (create issues)
   stories CSV  ───────────────────────────▶   Jira project
 (source of truth) ◀───────────────────────────  (issues)
        │             pull (refresh columns)
        │
        │  regenerate_html.py  (headless Chromium drives the app's own importer)
        ▼
   Standalone HTML app  ──lock_app.py──▶  view-only "locked" HTML  (what you distribute)
```

- **The CSV is authoritative.** `insignia-division-stories-jira-linked.csv` holds every story.
  Whether a row's `Jira Key` / `Jira URL` are filled decides what each script does.
- **Jira sync** (`jira_sync.py`) is optional — you can run the whole thing from the CSV alone.
  Use it to create Jira issues from blank rows (`push`) and to refresh the CSV from Jira (`pull`).
- **Regeneration** (`regenerate_html.py`) rebuilds the *entire* HTML app from the CSV plus a few
  overlay files (`settings.yaml`, `initiatives.csv`, `people.csv`), then hands you a locked,
  view‑only file to distribute.
- **Editing the app's UI/behaviour** (map, Priority tab, styling) is a separate workflow using
  `apply_source.py` (`--extract` / apply) — see [Editing the app itself](#editing-the-app-itself-wsjf-priority-tab--ui).

---

## Prerequisites & install

- **Python 3.10+** (developed on 3.12). Use `python3` on macOS/Linux.
- **git** to clone the repo.
- For HTML regeneration only: a **Chromium** browser downloaded by Playwright.

```bash
# 1. clone and enter the repo
git clone <this-repo-url>
cd jira-viewer

# 2. (recommended) a virtual environment
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate

# 3. Python dependencies
pip install -r requirements.txt

# 4. one-time: download the headless browser used by regenerate_html.py
python3 -m playwright install chromium
```

What each dependency is for:

| Package | Needed by | Notes |
|---|---|---|
| `requests` | `jira_sync.py` (push/pull) | the only hard dep if you *only* sync Jira |
| `playwright` + Chromium | `regenerate_html.py`, `export_tabs.py`, the browser tests | drives the app's own importer/serializer headlessly |
| `PyYAML` | `regenerate_html.py` | parses `settings.yaml` |
| `truststore` *(optional)* | `jira_sync.py` behind a TLS‑inspecting proxy | auto‑detected; or pass `--ca-bundle PATH` |

> **Which parts do I actually need?**
> - *Just want to look at / hand it out?* Open the shipped `.html` — no install needed.
> - *Sync with Jira?* `pip install requests` is enough.
> - *Rebuild the HTML from the CSV?* You need `playwright` + `chromium` + `PyYAML` too.

---

## Quick start (provided data)

The repo ships with a populated example (Insignia Financial). To rebuild the standalone HTML
from the provided CSV:

```bash
pip install -r requirements.txt
python3 -m playwright install chromium
python3 src/regenerate_html.py
```

This writes **`Insignia AI Strategy Map - regenerated.html`** — a locked, view‑only, offline
file. Open it in any browser. Switch to the **Priority** tab to see the WSJF studio scored from
the provided stories.

**Or use `make`** (a convenience wrapper over the same commands; run `make help` for the full list):

```bash
make install        # pip install + playwright install chromium
make build          # -> Insignia AI Strategy Map - regenerated.html
make deploy         # copy the regenerated HTML to app/index.html
```

To sync with Jira instead, see [Jira Sync](#jira-sync--push-and-pull).

---

## Using `make`

A `Makefile` wraps the common commands (each is just the `python3 src/…` invocation documented
elsewhere in this README). Run targets **from the repo root** — `make` does this for you. `make`
with no target, or `make help`, prints the list.

| Target | What it does | Runs |
|---|---|---|
| `make install` | Install Python deps **and** the headless Chromium browser | `pip install -r requirements.txt` + `python3 -m playwright install chromium` |
| `make build` | Rebuild the standalone HTML from the stories CSV | `python3 src/regenerate_html.py` |
| `make lock` | Build the view‑only locked bundle | `python3 src/lock_app.py` |
| `make deploy` | Copy the built `*regenerated*.html` to `app/index.html` | (run `make build` first) |
| `make test` | Run the full test suite | `python3 -m pytest tests/ -q` |
| `make extract` | Extract the editable app source | `python3 src/apply_source.py --extract` |
| `make apply` | Apply `src/strategy-map.src.html` back into the bundle | `python3 src/apply_source.py` |
| `make seed` | Seed `initiatives.csv` / `settings.yaml` / `people.csv` from the app | `python3 src/export_tabs.py` |
| `make push` | Create Jira issues for blank CSV rows (needs `.env`) | `python3 src/jira_sync.py push` |
| `make pull` | Refresh the stories CSV from linked Jira issues | `python3 src/jira_sync.py pull` |
| `make clean` | Remove generated build outputs (regenerated/locked HTML, `divisions*.csv`, error PNGs, `__pycache__`, `.pytest_cache`) | — |

**Common flows**

```bash
make install && make build && make deploy      # first run: set up, build, publish to app/index.html
make build deploy                              # rebuild after a CSV change, then re-deploy
make extract                                   # then edit src/strategy-map.src.html …
make apply && make test                        # … apply your edit and verify
```

**Notes**

- `make deploy` does **not** rebuild first — it copies whatever `*regenerated*.html` is on disk
  (and errors with a hint if there is none). Use `make build deploy` for a fresh publish.
- Override the interpreter with `PYTHON=…` if `python3` isn't your default, e.g.
  `make build PYTHON=python3.12`.
- `make build`, `lock`, `deploy`, `seed` need the regeneration extras (`playwright` + Chromium +
  `PyYAML`); `make install` sets them up. `make push`/`pull` need only `requests` and a `.env`.

---

## The stories CSV — the single source of truth

Default file: **`insignia-division-stories-jira-linked.csv`** (override with `--csv`).

**Columns (exactly, in order):**

```
#, Division, Opportunity, AI-fit, Key people, Systems, Themes, Summary, Description, Jira Key, Jira URL
```

- **UTF‑8 with BOM**, every field quoted.
- `Opportunity` is the Jira issue **title**.
- `AI-fit` is one of `High` / `Medium-High` / `Medium` / `Medium-Low` (drives the legend colour).
- `Systems` and `Themes` are `;`‑ or `,`‑separated lists (used for WSJF capability + reuse scoring).
- `Description` is the issue body. A leading `TLDR; …` line, if present, is split off into the
  card summary; the rest becomes the story body used by WSJF scoring.
- `Jira Key` / `Jira URL` are written by `push` and read by `pull`. Leave both **blank** for a
  row you want `push` to create.

`seed-template.csv` is the header row alone — copy it to start a fresh backlog.

---

## Jira Sync — `push` and `pull`

Jira sync needs `requests` and a `.env` file with your Jira Cloud credentials.

```bash
cp .env.example .env      # then edit .env
```

`.env` (gitignored — never commit real secrets):

```
JIRA_BASE_URL=https://yourcompany.atlassian.net   # no trailing slash
JIRA_EMAIL=you@company.com
JIRA_API_TOKEN=...        # https://id.atlassian.com/manage-profile/security/api-tokens
JIRA_PROJECT_KEY=ABC      # the project issues are created in
JIRA_ISSUE_TYPE=Story     # must already exist in that project
```

> Scoped API tokens need **read + write:jira-work**.

### `push` — create Jira issues for blank rows

A row is eligible only when **both** `Jira Key` and `Jira URL` are blank. Eligible rows become
Jira issues (title = `Opportunity`, body = `Description` + a metadata context block, plus
`div-*` / `ai-fit-*` / `theme-*` labels). The created key + URL are written back into the CSV,
saved after each create. Rows already linked are skipped. A row with only **one** of Key/URL
filled is inconsistent — reported and skipped, never duplicated.

```bash
python3 src/jira_sync.py push --dry-run           # preview payloads, no API calls
python3 src/jira_sync.py push                       # create + write Key/URL back to the CSV
python3 src/jira_sync.py push --assign --verify     # set assignee (when unambiguous), verify each create
```

Other flags: `-v/--verbose`, `--csv PATH`, `--ca-bundle PATH`. A per‑run audit log is appended
to `<csv>.upload-log.csv` (gitignored).

### `pull` — refresh columns from linked issues

The inverse. For each row with a `Jira URL`, the issue is fetched and the content columns are
refreshed from it (title → `Opportunity`, body → `Description`, and Division / AI‑fit / Key
people / Systems / Themes / Summary from the description's context block). Rows without a URL are
untouched.

```bash
python3 src/jira_sync.py pull --dry-run           # show per-cell diff, no write
python3 src/jira_sync.py pull                       # apply
```

Also accepts `--csv PATH`, `-v/--verbose`, `--ca-bundle PATH`.

---

## Regenerate & lock the app

`regenerate_html.py` rebuilds the **entire** page from files by driving the app's own CSV
import + "Download standalone HTML" in headless Chromium (the data is compressed inside the
bundle, so this reuses the app's real serializer).

```bash
python3 src/regenerate_html.py                     # -> "Insignia AI Strategy Map - regenerated.html"
python3 src/regenerate_html.py --headed            # watch it run in a visible browser
python3 src/regenerate_html.py --csv X --html Y --out Z
```

It composes the page from:

- **`settings.yaml`** — the header (company, title, intro), the centre/hub node (name, tagline,
  and its Jira board `url`), the AI‑fit legend (labels + colours), and per‑division colour /
  tagline / background overrides. Every section is optional — it's an overlay, so anything you
  omit keeps the app's current value.
- **Divisions** are derived automatically from the stories CSV: one per distinct `Division`, with
  Systems/Themes = the deduped union across that division's stories, and colour/tagline/background
  from `settings.yaml` (an auto‑assigned palette colour for any division you don't override).
  Written to `divisions.csv` (generated, gitignored).
- **`initiatives.csv`** — a standalone editable file of cross‑cutting initiatives.
- **`people.csv`** (`Division, Name, Role, Relevance`) — division key people. Authoritative when
  present.

Seed the editable overlay files from the app's current content, then regenerate:

```bash
python3 src/export_tabs.py       # writes initiatives.csv, settings.yaml, people.csv
python3 src/regenerate_html.py   # stories CSV + initiatives.csv + settings.yaml + people.csv -> HTML
```

### The output is locked (view‑only)

The shipped file is **view‑only**: the Data tabs have no upload/edit/add/delete controls (data
changes only by re‑running `regenerate`), while an **Export CSV** download is kept for viewers.
In the Priority tab, the scoring grid and the API‑key field become read‑only and the CSV upload
is hidden.

- The lock is baked into the app's own source by `lock_app.py`, which produces
  **`Insignia AI Strategy Map - locked.html`** (generated, gitignored). `regenerate` builds it
  automatically if missing.
- `regenerate` is **two‑stage**: it builds the exact internal data by importing the CSVs into the
  editable source (headless), then injects that data into the locked bundle and downloads — so
  nothing is lost (per‑division `gaps` / `nextSteps` and catalogues that aren't in any CSV ride
  along).
- The editable source file `Insignia AI Strategy Map - Jira linked.html` is an **internal build
  tool only** — never the thing you distribute; the locked output is.

```bash
python3 src/lock_app.py          # (optional) build the locked bundle explicitly
python3 src/regenerate_html.py   # builds it if missing, then ships the locked output
```

---

## Fresh setup from a *different* Jira & project

You can point the whole toolkit at your own Jira and your own content. There are two paths:
start from a blank backlog and let Jira issues be created for you, or start from an existing Jira
project and pull it down. Either way you end up with a populated stories CSV, then regenerate.

### Step 0 — one‑time install

Follow [Prerequisites & install](#prerequisites--install) (`pip install -r requirements.txt`,
`python3 -m playwright install chromium`).

### Step 1 — point at your Jira

```bash
cp .env.example .env
```

Edit `.env` for **your** site and project:

```
JIRA_BASE_URL=https://acme.atlassian.net
JIRA_EMAIL=you@acme.com
JIRA_API_TOKEN=<your token>
JIRA_PROJECT_KEY=PLAT          # your project's key
JIRA_ISSUE_TYPE=Story          # an issue type that EXISTS in that project
```

> The project key and issue type must already exist in your Jira. `push` does not create
> projects or issue types.

### Step 2 — get your content into the stories CSV

Pick **one**:

**Path A — you have content but no Jira issues yet (create them):**

```bash
cp seed-template.csv my-backlog.csv
# Fill each row's columns; leave "Jira Key" and "Jira URL" BLANK.
# Columns: #, Division, Opportunity, AI-fit, Key people, Systems, Themes, Summary, Description, Jira Key, Jira URL

python3 src/jira_sync.py push --csv my-backlog.csv --dry-run   # preview
python3 src/jira_sync.py push --csv my-backlog.csv             # creates issues, writes Key/URL back
```

**Path B — you already have issues in Jira (pull them):**
Put one row per issue in a CSV with its `Jira URL` filled (Division/Opportunity/etc. can be
blank — `pull` fills them), then:

```bash
python3 src/jira_sync.py pull --csv my-backlog.csv --dry-run   # per-cell diff
python3 src/jira_sync.py pull --csv my-backlog.csv             # apply
```

> **Skipping Jira entirely?** You don't have to use Jira at all. Just author `my-backlog.csv`
> by hand (leave the two Jira columns blank) and go straight to Step 4.

### Step 3 — brand it (optional but recommended)

Edit `settings.yaml` for your organisation. At minimum set:

```yaml
header:
  company: Acme Corp
  title: Platform AI Prioritisation
  intro: One-line description shown under the title.
hub:
  name: AI Strategy
  tagline: Your programme tagline
  url: https://acme.atlassian.net/jira/software/c/projects/PLAT/boards/123   # "open board" link on the hub
legend:
  title: AI-fit rating
  levels:
    - { label: High,        color: '#e0674c' }
    - { label: Medium-High, color: '#e3a24b' }
    - { label: Medium,      color: '#5aa9a0' }
    - { label: Medium-Low,  color: '#7d8ca3' }
# Optional per-division overrides (colour / tagline / background). Omit and a palette colour is auto-assigned.
divisions:
  Platform Engineering:
    colour: '#3f7c8c'
    tagline: Core platform & tooling
    background: Free-text shown when the division is selected.
```

`initiatives.csv` and `people.csv` are optional overlays — leave them empty/absent if you don't
need cross‑cutting initiatives or per‑division people.

### Step 4 — build your standalone app

```bash
python3 src/regenerate_html.py --csv my-backlog.csv --out "Acme AI Prioritisation.html"
```

- Divisions, Systems/Themes catalogues, and the whole map are derived automatically from
  `my-backlog.csv`.
- The **WSJF Priority tab works with no extra configuration** — it scores your stories from their
  text (Description/Summary/Themes/Systems) and ranks them. Financial scoring categories are off
  by default; turn them on in the Priority → **Setup** tab.
- The result is a locked, offline, single‑file HTML you can email or host anywhere.

### Step 5 — iterate

Change stories in Jira → `pull` → `regenerate`. Or edit the CSV directly → `regenerate`. The CSV
stays the source of truth; the HTML is always rebuilt from it.

> **Note on filenames.** The defaults are Insignia‑branded
> (`insignia-division-stories-jira-linked.csv`, `Insignia AI Strategy Map - Jira linked.html`).
> They're just defaults — pass `--csv` / `--html` / `--out` to use your own names. The visible
> title/company come from `settings.yaml`, not the filename.

---

## Editing the app itself (WSJF Priority tab & UI)

Everything above changes the *data*. To change the app's *UI or behaviour* (the map, the Priority
views, styling), you edit the app's source and re‑apply it into the bundle. **There is no separate
front‑end build step** — the app is authored directly inside the single HTML file.

### The single‑file bundle format

`Insignia AI Strategy Map - Jira linked.html` is a "bundled page":

- `<script type="__bundler/manifest">` — a JSON map of resources (`{uuid: {mime, compressed, data}}`);
  `data` is base64 of gzip. Holds the framework runtime, fonts, and the app data.
- `<script type="__bundler/template">` — the **editable HTML source** (a `dc-runtime` component in
  `<script type="text/x-dc" data-dc-script>`), stored as a JSON string.
- A self‑copy of that source lives in `window.__PRISTINE_HTML` inside one JS resource; the app's
  own "Download standalone HTML" serializer rebuilds shareable copies from it.

### Extract → edit → apply

```bash
python3 src/apply_source.py --extract                # -> src/strategy-map.src.html (editable)
# ...edit src/strategy-map.src.html in your editor...
python3 src/apply_source.py                          # writes it back into the bundle (both copies)
python3 -m pytest tests/ -q                      # ALWAYS run the full suite after an edit
```

`apply_source.py` writes your edits into **both** the runtime `template` block and the authoring
`__PRISTINE_HTML` copy, applying the runtime↔authoring transform so the app's regenerate/lock
serializer keeps working. It also supports `--extract`, `--bundle PATH`, `--src PATH`.

> ⚠️ **Always verify with the full `pytest` suite after an edit**, not just a quick check — the
> `test_lock_app` / `test_regenerate` tests are what catch a broken serializer copy. (They can be
> mildly flaky on a cold first run because of the large bundle download; re‑run if one times out.)

### Supporting tools

- `bundle_resources.py` — copy a resource (font/JS) from one bundle's manifest into another, or
  remove one by uuid.

---

## The WSJF Priority tab in depth

The Priority tab is a full WSJF studio, scored automatically from the shared stories store (no
manual scoring required to get started).

- **Exec** — a Top‑10 (plus a 15‑story watchlist), KPI cards (sprint load, must‑do, needs‑evidence,
  median confidence), a **what‑if weighting** panel (drag a weight and the ranking re‑sorts live),
  and the Top‑10 investment mix by strategic pillar.
- **Table** — an editable scoring grid; per‑category score overrides and job‑size are saved to your
  browser (`localStorage`) and override the auto‑score. **RESET ALL** clears overrides; **EXPORT
  CSV** downloads the ranked backlog.
- **Matrix** — Cost‑of‑Delay against T‑shirt job size (top‑left is the buy zone).
- **Bubble** — a swimlane per division, x‑position by WSJF, chip weight by job size.
- **Heat** — every story against all nine scoring categories.
- **Stair** — stories packed in WSJF order into fixed‑capacity sprints (capacity slider).
- **Setup** — replace the shared store by dropping a Jira CSV export; optional LLM scoring
  endpoint/key (held in session storage only); financial‑category toggles; the pillar mapping.

**Shared store & map integration.** All views and the map read one stories array. On the map, a
division's cards fan out in WSJF order with a `WSJF x.x · #rank` badge, a **◆ Priority heat**
toggle tints division nodes by their share of the top‑25, and **View in Priority →** on a selected
division opens the Priority tab scoped to it (a clearable chip restores the full backlog).

**Scoring is heuristic and transparent.** Each category (Strategic Alignment, Customer Experience,
Risk Reduction, Platform Reuse, AI Capability Lift, Employee Experience, plus optional financial
ones) is scored 1–5 from evidence in the story text; Cost of Delay is their weighted sum and WSJF =
CoD ÷ job size. Confidence reflects evidence quality and how many hard numbers back a story.

---

## File reference

The source code lives in **`src/`**; data/config stay in the repo root. `app/` is the deploy
directory (`make deploy` writes `app/index.html`).

| File | Role |
|---|---|
| `insignia-division-stories-jira-linked.csv` | **The stories CSV** — single source of truth |
| `seed-template.csv` | Empty stories‑CSV header row to start a fresh backlog |
| `Insignia AI Strategy Map - Jira linked.html` | Editable app bundle — **internal build tool**, not for distribution |
| `Insignia AI Strategy Map - locked.html` | View‑only shipped bundle (generated, gitignored) |
| `Insignia AI Strategy Map - regenerated.html` | `regenerate` output (generated, gitignored) |
| `app/index.html` | Deployed page — `make deploy` copies the regenerated HTML here (gitignored) |
| `Makefile` | Convenience targets (`make help` lists them) |
| `src/jira_sync.py` | CLI: `push` / `pull` |
| `src/jira_common.py` | Shared: `.env` loader, CSV I/O, markdown⇄ADF, context‑block round‑trip, labels, Jira client + preflight |
| `src/regenerate_html.py` | Rebuild the whole HTML from stories CSV + `initiatives.csv` + `settings.yaml` + `people.csv` |
| `src/settings_common.py` | Settings load, division derivation, settings + people overlay |
| `src/export_tabs.py` | Seed `initiatives.csv` / `settings.yaml` / `people.csv` from the app's current content |
| `src/lock_app.py` | Bake the view‑only lock guard into the app source → locked bundle |
| `src/apply_source.py` | Extract (`--extract`) / apply `src/strategy-map.src.html` ⇄ the bundle (runtime + pristine copies) |
| `src/strategy-map.src.html` | The editable app source (extracted; edit here, then `make apply`) |
| `src/bundle_resources.py` | Copy/remove manifest resources between bundles |
| `src/bundle_common.py` | Decode/edit/re‑encode a single bundle resource |
| `settings.yaml` | Header / hub / legend / per‑division overrides |
| `initiatives.csv` | Standalone editable cross‑cutting initiatives |
| `people.csv` | Division key people (name, role, relevance) |
| `.env.example` | Jira credentials template |
| `requirements.txt` | Python dependencies |

---

## Tests

```bash
python3 -m pytest tests/ -q
```

The suite covers the Jira sync helpers, the CSV round‑trips, the bundle tooling (extract/apply
byte‑fidelity, resource copy/remove, structural invariants), and — via headless Chromium — that
`regenerate` reflects the CSV and the locked output has no mutation controls after download. Run
it after any change to a Python script or the app source.

---

## Troubleshooting

- **`python: command not found`** — use `python3` (and `pip`/`python3 -m pip`).
- **Playwright can't find a browser** — run `python3 -m playwright install chromium` once.
- **Jira auth fails** — check `JIRA_EMAIL` / `JIRA_API_TOKEN`; scoped tokens need
  read + write:jira‑work; `JIRA_ISSUE_TYPE` must exist in `JIRA_PROJECT_KEY`.
- **Corporate TLS proxy (Zscaler/Netskope)** — `pip install truststore` (auto‑detected) or pass
  `--ca-bundle /path/to/corp-ca.pem` to `jira_sync.py`.
- **`regenerate` / a browser test times out on the download** — the bundle is large; the first
  cold download can be slow. Re‑run; it's reliable when warm.
- **Nothing shows in a `file://` preview but works elsewhere** — some preview panes render the
  regenerated/locked file as a static snapshot instead of running its inlined runtime. Open it in
  a real browser tab.
