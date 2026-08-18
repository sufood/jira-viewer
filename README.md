# AI Strategy Map + WSJF Priority — Jira ⇄ CSV ⇄ Standalone-HTML Toolkit

A self-contained, single-file HTML app that visualises a portfolio of opportunities as an
interactive **strategy map** and a **WSJF prioritisation studio**, driven entirely by one CSV.
A small Python toolkit keeps that CSV in sync with Jira (create issues, pull updates) and
rebuilds the shippable HTML from the CSV.

- **Strategy map** — divisions fan out around a hub; click a division to see its opportunities,
  people, gaps and next steps. In the **Initiatives** lens, clicking an initiative drills into its
  story‑instances grouped by the division they live in (an initiative spans many divisions).
- **Priority tab** — a full **WSJF (Weighted Shortest Job First)** studio: an executive Top‑10,
  an editable scoring grid, a value/effort matrix, bubble/heatmap/sprint‑staircase views, and
  live "what‑if" weighting — all scored automatically from the story text.
- **One shared store** — the map and every Priority view read the *same* stories, so a
  division's cards fan out by funding‑gate status then WSJF, and a "priority heat" overlay tints
  the map by WSJF.

The shipped artifact is a **single `.html` file** with everything embedded (JS, fonts, data).
It needs no server and works offline, including from a `file://` path.

---

## Table of contents

1. [How it fits together](#how-it-fits-together)
2. [Prerequisites & install](#prerequisites--install)
3. [Quick start (provided data)](#quick-start-provided-data)
4. [Using `make`](#using-make)
5. [The stories CSV — the single source of truth](#the-stories-csv--the-single-source-of-truth)
6. [Jira Sync — `push`, `pull` and `import`](#jira-sync--push-pull-and-import)
7. [Authoring Jira stories for optimal round-trip (the context block)](#authoring-jira-stories-for-optimal-round-trip-the-context-block)
8. [Regenerate & lock the app](#regenerate--lock-the-app)
9. [Fresh setup from a *different* Jira & project](#fresh-setup-from-a-different-jira--project)
10. [Editing the app itself (WSJF Priority tab & UI)](#editing-the-app-itself-wsjf-priority-tab--ui)
11. [The WSJF Priority tab in depth](#the-wsjf-priority-tab-in-depth)
12. [File reference](#file-reference)
13. [Tests](#tests)
14. [Troubleshooting](#troubleshooting)

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

# 3b. behind a corporate TLS-inspecting proxy (Zscaler / Netskope etc.)? install
#     truststore so Python trusts your OS/Keychain cert store (see note below):
pip install truststore

# 4. one-time: download the headless browser used by regenerate_html.py
python3 -m playwright install chromium
```

> **Behind a corporate proxy (Zscaler / Netskope / etc.)?** If a Jira command dies with
> `SSLCertVerificationError: ... self-signed certificate in certificate chain`, your proxy is
> intercepting HTTPS with a root CA that Python doesn't trust. Fix it once with
> `pip install truststore` — `jira_sync.py` auto-detects it and verifies against your **macOS
> Keychain / Windows cert store** (where IT has installed that root CA). `make install` now does
> this for you. Alternatively pass `--ca-bundle /path/to/corp-ca.pem` to any Jira command.

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
| `make help` | Print the target list (same as bare `make`) | hard-coded summary echo |
| `make install` | Install Python deps, `truststore` (corporate-proxy TLS), **and** the headless Chromium browser | `pip install -r requirements.txt` + `pip install truststore` + `python3 -m playwright install chromium` |
| `make build` | **Assemble the bundle from source, then render the HTML** (override `CSV=` / `OUT=` / `HTML=`) | `python3 src/build_bundle.py` + `python3 src/regenerate_html.py …` |
| `make bundle` | (Re)assemble the app bundle from `src/` only, no render | `python3 src/build_bundle.py` |
| `make lock` | Build the view‑only locked bundle | `python3 src/lock_app.py` |
| `make deploy` | Copy the built `*regenerated*.html` to `app/index.html` (errors if none — run `make build` first) | shell `cp` |
| `make test` | Run the full test suite | `python3 -m pytest tests/ -q` |
| `make seed` | Seed `initiatives.csv` / `settings.yaml` / `people.csv` from the app | `python3 src/export_tabs.py` |
| `make push` | Create Jira issues for blank CSV rows — **prompts `y/N` (default N) before writing to Jira**; `YES=1` skips it (needs `.env`) | `python3 src/jira_sync.py push` |
| `make pull` | Refresh the stories CSV from linked Jira issues — **prompts before overwriting existing values**; `YES=1` skips it (needs `.env`) | `python3 src/jira_sync.py pull` |
| `make import` | Read **all** issues in one or more projects/JQL into a CSV (`PROJECT=AITR` or `PROJECT=AITR,AIENG` / `CSV=…` / `BOARD=…`; needs `.env`) | `python3 src/jira_sync.py import …` |
| `make clean` | Remove generated build outputs (assembled bundle, regenerated/locked HTML, `divisions*.csv`, error PNGs, `__pycache__`, `.pytest_cache`) | shell `rm` |
| `make engine-extract` | Maintenance: re‑vendor `src/engine/` from a bundle (runtime/fonts changed) | `python3 src/decompose_bundle.py` |
| `make apply` | Low‑level: patch `src/strategy-map.src.html` into the existing bundle **in place** (normal edits use `make build`) | `python3 src/apply_source.py` |
| `make extract` | Low‑level: pull the app source out of the bundle back into `src/strategy-map.src.html` | `python3 src/apply_source.py --extract` |

**One runnable example per target**

```bash
make help                                                 # list targets (same as bare `make`)
make install                                              # deps + truststore + headless Chromium
make bundle                                               # assemble the bundle only, no render
make build                                                # assemble + render -> "Insignia AI Strategy Map - regenerated.html"
make build CSV=ai-topics.csv OUT="AITR Strategy Map.html" # …the same, for a different dataset
make lock                                                 # -> "Insignia AI Strategy Map - locked.html"
make deploy                                               # copy the regenerated HTML -> app/index.html
make test                                                 # run the pytest suite (uses headless Chromium)
make seed                                                 # write initiatives.csv / settings.yaml / people.csv from the app
make push                                                 # create Jira issues for blank rows — prompts y/N first (needs .env)
make push YES=1                                            # …skip the prompt (unattended / CI)
make pull                                                 # refresh the CSV — prompts before overwriting existing values (needs .env)
make import PROJECT=AITR CSV=ai-topics.csv BOARD=6393     # import a project into a CSV (needs .env)
make clean                                                # delete generated outputs (CSV/HTML sources are kept)
make engine-extract                                       # maintenance: re-vendor src/engine/ from a bundle
make apply                                                # low-level: patch app source into the bundle in place
make extract                                              # low-level: extract app source from the bundle
```

**Common flows**

```bash
make install && make build && make deploy      # first run: set up, build, publish to app/index.html
make build deploy                              # rebuild after any change, then re-deploy
make build CSV=ai-topics.csv OUT="AITR Strategy Map.html"   # build a different dataset (see below)
# edit src/strategy-map.src.html, then:
make build && make test                        # app-source edits flow through automatically
```

**Notes**

- **Which CSV does `build` use?** With no override, `make build` (and `regenerate_html.py`) uses the
  default Insignia stories CSV — **`insignia-division-stories-jira-linked.csv`** — and writes the
  default output **`Insignia AI Strategy Map - regenerated.html`**. Point it at another dataset with
  `CSV=` (and `OUT=` to name the output). For example, to build the **AITR** project you imported into
  `ai-topics.csv`:

  ```bash
  make import PROJECT=AITR CSV=ai-topics.csv                    # pull AITR issues into ai-topics.csv
  make build  CSV=ai-topics.csv OUT="AITR Strategy Map.html"    # build that dataset
  ```

  (The raw form is `python3 src/regenerate_html.py --csv ai-topics.csv --out "AITR Strategy Map.html"`;
  `--csv` / `--out` default to the Insignia names when omitted.)
- **`make build` always assembles the bundle from source first**, so it can never ship a stale HTML —
  whether you changed data (`settings.yaml`, a CSV) or the app source (`src/strategy-map.src.html`), one
  `make build` reflects it. There is no separate `apply` step.
- `make deploy` does **not** rebuild first — it copies whatever `*regenerated*.html` is on disk
  (and errors with a hint if there is none). Use `make build deploy` for a fresh publish.
- Override the interpreter with `PYTHON=…` if `python3` isn't your default, e.g.
  `make build PYTHON=python3.12`.
- `make build`, `lock`, `deploy`, `seed` need the regeneration extras (`playwright` + Chromium +
  `PyYAML`); `make install` sets them up. `make push`/`pull`/`import` need only `requests` and a `.env`.
- **`make apply` / `make extract` are low-level maintenance** and rarely needed now that `make build`
  assembles from source. `apply` patches the app source into an **existing** bundle in place (so it
  needs a bundle on disk — `make bundle` or `make build` first; `make clean` deletes it), and `extract`
  copies the app source back out of the bundle into `src/strategy-map.src.html`. For everyday UI/logic
  edits, edit `src/strategy-map.src.html` and run `make build` — never `make apply`.

---

## The stories CSV — the single source of truth

Default file: **`insignia-division-stories-jira-linked.csv`** — this is what every command uses when
you don't say otherwise. Override it per command with `--csv PATH` (or `CSV=PATH` via `make`), e.g. the
AITR dataset: `make build CSV=ai-topics.csv OUT="AITR Strategy Map.html"`.

**Columns (exactly, in order):**

```
#, Division, Initiative, Opportunity, AI-fit, Status, Key people, Systems, Themes, Summary, Description, Jira Key, Jira URL
```

- **UTF‑8 with BOM**, every field quoted.
- `Division` and `Initiative` are two **independent axes**. A story belongs to exactly one
  `Division`, and is one *instantiation* of exactly one `Initiative`. The same initiative
  (e.g. *Knowledge Bases*, *CGT Calculator*) can appear across many divisions — the
  initiative↔division spread is derived through the stories, not stored. `Initiative` is optional
  and may be blank.
- `Opportunity` is the Jira issue **title**.
- `AI-fit` is one of `High` / `Medium-High` / `Medium` / `Medium-Low` (drives the legend colour).
- `Status` is the funding‑gate lifecycle: `Funded` / `Endorsed` / `Prioritised` / `Parked`
  (an ordinal ladder). In the map, a division's cards sort by `Status` in that order first, then by
  WSJF‑desc within each band; each card shows a status chip and **Parked** cards are dimmed. Blank
  or unknown values sort alongside `Prioritised` and show no chip.
- `Systems` and `Themes` are `;`‑ or `,`‑separated lists (used for WSJF capability + reuse scoring).
- `Description` is the issue body. A leading `TLDR; …` line, if present, is split off into the
  card summary; the rest becomes the story body used by WSJF scoring.
- `Jira Key` / `Jira URL` are written by `push` and read by `pull`. Leave both **blank** for a
  row you want `push` to create.

> **How each field travels to Jira.** Exact, round‑tripped values (`Division`, `Initiative`,
> `AI-fit`, `Status`, `Key people`, `Systems`, `Themes`, `Summary`) ride in the machine‑readable
> **context block** at the bottom of the Description. Filterable facets are *also* emitted as
> slug **labels**: `div-*`, `ai-fit-*`, `theme-*`, and now `init-*` and `status-*` (the latter two
> only when a value is present). Scores/sizes with a numeric value belong in the context block or a
> Jira custom field — never a label.

`seed-template.csv` is the header row alone — copy it to start a fresh backlog.

---

## Jira Sync — `push`, `pull` and `import`

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

> Scoped API tokens need **read + write:jira-work** (read-only is enough for `pull` / `import`).
>
> **Corporate proxy?** If any command fails with `SSLCertVerificationError: ... self-signed
> certificate in certificate chain`, run `pip install truststore` (or `make install`) once — see
> [Prerequisites & install](#prerequisites--install). Or pass `--ca-bundle /path/to/corp-ca.pem`.

### `push` — create Jira issues for blank rows

A row is eligible only when **both** `Jira Key` and `Jira URL` are blank. Eligible rows become
Jira issues (title = `Opportunity`, body = `Description` + a metadata context block, plus
`div-*` / `ai-fit-*` / `theme-*` labels). The created key + URL are written back into the CSV,
saved after each create. Rows already linked are skipped. A row with only **one** of Key/URL
filled is inconsistent — reported and skipped, never duplicated.

```bash
python3 src/jira_sync.py push --dry-run           # preview payloads, no API calls
python3 src/jira_sync.py push                       # asks to confirm, then creates + writes Key/URL back
python3 src/jira_sync.py push --assign --verify     # set assignee (when unambiguous), verify each create
python3 src/jira_sync.py push --yes                 # skip the prompt (unattended / CI)
```

> **Confirmation before it writes to Jira.** Because `push` creates real issues (an irreversible
> external change), it prints how many it will create and asks `Proceed? [y/N]` — the default is
> **No**, so pressing Enter (or anything other than `y`/`yes`) aborts without creating anything.
> Pass `-y`/`--yes` to skip the prompt for unattended runs. On a non-interactive stdin (a pipe,
> cron, CI) it **declines** unless `--yes` is given, so nothing is created by accident. `--dry-run`
> never prompts (it makes no API calls).

Other flags: `-v/--verbose`, `--csv PATH`, `--ca-bundle PATH`, `-y/--yes`. A per‑run audit log is
appended to `<csv>.upload-log.csv` (gitignored).

### `pull` — refresh columns from linked issues

The inverse. For each row with a `Jira URL`, the issue is fetched and the content columns are
refreshed from it (title → `Opportunity`, body → `Description`, and Division / AI‑fit / Key
people / Systems / Themes / Summary from the description's context block). Rows without a URL are
untouched.

```bash
python3 src/jira_sync.py pull --dry-run           # show per-cell diff, no write
python3 src/jira_sync.py pull                       # apply (asks first if it would overwrite existing values)
python3 src/jira_sync.py pull --yes                 # skip the prompt (unattended / CI)
```

> **Confirmation before it overwrites existing values.** If `pull` would replace one or more
> **non-empty** cells that already hold data, it lists them and asks `Proceed? [y/N]` — default
> **No**, so anything but `y`/`yes` aborts and writes nothing. Merely *filling blank* cells is not
> a loss, so it writes straight through with no prompt. Pass `-y`/`--yes` to skip the prompt; a
> non-interactive stdin declines unless `--yes` is given. `--dry-run` shows the diff and never
> prompts.

Also accepts `--csv PATH`, `-v/--verbose`, `--ca-bundle PATH`, `-y/--yes`.

### `import` — read a whole project (or JQL) into a new CSV

`push`/`pull` only touch rows you already have. `import` is how you **start** from a project:
nominate an issue-key prefix — e.g. `AITR-*`, whose Jira project key is simply `AITR` — and it reads
**every** matching issue into a fresh jira-linked CSV, one row per issue, ready for `regenerate`.

It searches with JQL through Jira's token-paginated
[`/rest/api/3/search/jql`](https://confluence.atlassian.com/jirakb/run-jql-search-query-using-jira-cloud-rest-api-1289424308.html)
endpoint (the older `/search` GET is deprecated), so it handles projects of any size. A read-only
API token (`read:jira-work`) is enough — it never writes to Jira.

```bash
python3 src/jira_sync.py import --project AITR --csv ai-topics.csv --dry-run   # list what it'd import
python3 src/jira_sync.py import --project AITR --csv ai-topics.csv             # write the CSV
# or with make:
make import PROJECT=AITR CSV=ai-topics.csv
```

Each issue maps to a row: `summary → Opportunity`, `description → Description`. For issues **this
toolkit created**, the metadata context block round-trips fully (Division / Initiative / AI-fit /
Status / Key people / Systems / Themes / Summary come straight back). For **foreign** issues that
have no context block, only those two content columns are known, so:

- `--division NAME` (default **`N/A`**) is assigned to every row that doesn't carry its own
  Division. Keep a non-empty value: the strategy map **drops blank-Division rows**, so `N/A` keeps
  every imported issue visible under one node (all Priority/WSJF views work regardless). Re-bucket
  later by editing the `Division` column and re-running `regenerate`.
- `--ai-fit LEVEL` (optional, e.g. `Medium`) gives foreign rows a defined legend colour on the map.

`Jira Key` / `Jira URL` are filled for every row, so a subsequent `pull` keeps the CSV in sync.
`--project` takes one key or several — `--project AITR,AIENG`, or the flag
repeated. Several keys become `project in (AITR, AIENG)`; every key is checked
for visibility before the import runs, and all unreachable ones are reported
together. `push` still targets exactly one project, so `JIRA_PROJECT_KEY` must
name a single key.

With several projects there is no "first board on the project", so the board is
resolved as `--board`, then `kanban.board` in `settings.yaml`, then the first
board on the first key.

Also accepts `--jql "…"` (overrides `--project` for subsets/components/labels),
`-v/--verbose`, `--csv PATH`, `--ca-bundle PATH`.

Then build the app from the imported CSV — `make build` assembles the bundle from source first, so it
always includes the latest app-source features (like the kanban marker):

```bash
make build CSV=ai-topics.csv OUT="AI Topics.html"
```

#### Kanban progress marker (Stage + Swimlane)

`import` also captures each issue's **board position** so the map can show a
progress stepper on every card. It reads the board's column order via the Agile
API (`--board ID`, or the first board on the project) and maps each issue's
status to a column → the `Stage` column. It reconstructs the query-**swimlane**
each issue sits in by running each lane's JQL (Jira's API doesn't expose that),
first-match-wins → the `Swimlane` column. Both are configured in the `kanban:`
block of `settings.yaml`:

```yaml
kanban:
  board: 6393
  stages: [IDEAS, INTAKE, DISCOVER, TRIAGE & ROUTE, DESIGN, BUILD, MEASURE, DONE]
  swimlanes:
  - { name: Expedite,        jql: priority = Highest,   colour: '#e3a24b' }
  - { name: Blocked,         jql: flagged is not EMPTY, colour: '#c0504d' }
  - { name: Everything Else,  jql: null,                colour: '#8a94a2' }   # default lane
```

**Where it shows.** Open the map and **click a division** so its cards fan out — the marker sits at
the **footer of each opportunity card**: a segmented stepper (one segment per board column, filled
through the current `Stage`), **tinted by the `Swimlane`** (grey = *Everything Else*, amber =
*Expedite*, red = *Blocked*), with the stage name (`BUILD · 6/8`) and, for non-default lanes, a
coloured swimlane tag. It's the per-card marker only — there's no separate kanban-board view.

**Build a map with the marker (end to end):**

```bash
# 1. import WITH kanban capture — writes the Stage + Swimlane columns (needs .env; --board is the
#    Agile board id, e.g. AITR's is 6393). Watch the output for "Board 6393: 8 columns (…)".
python3 src/jira_sync.py import --project AITR --board 6393 --csv ai-topics.csv --dry-run   # preview
python3 src/jira_sync.py import --project AITR --board 6393 --csv ai-topics.csv             # write CSV

# 2. rebuild the map from that CSV, then hard-reload the file in the browser (Cmd+Shift+R)
make build CSV=ai-topics.csv OUT="AITR Strategy Map.html"
```

> The marker only appears when the story has a `Stage` **and** that value is one of `kanban.stages`.
> An older CSV imported *before* this feature (or with `--no-kanban`) has no `Stage` column, so no
> marker shows — re-run the `import` above to populate it.

> Two things to keep aligned: `settings.yaml` → `kanban.stages` must match the
> board's real column names (import prints them, e.g. `Board 6393: 8 columns
> (…)`), and the `swimlanes` JQL should match your board's actual lane queries
> (copy them from *Board settings → Swimlanes*). A `Stage` not in `kanban.stages`
> just renders no marker; it never breaks the card.

---

## What makes a Jira issue show up in the map

The map is built from the stories CSV, and `import` fills that CSV from Jira. So "will my Jira issue
appear, and appear *well*?" comes down to a few fields. Checklist:

1. **It has to be in the import.** `import --project AITR` pulls **every** issue in the project (stories,
   tasks, epics — all of them). Narrow it with `--jql`, e.g. stories only:
   `--jql "project = AITR AND issuetype = Story"`. If an issue isn't in the project/JQL, it isn't in the map.

2. **Give it a Division — or it's dropped.** The map is organised by Division, and **rows with a blank
   Division do not appear on the map.** How Division gets set:
   - Issues **created by this toolkit** (`push`) carry a hidden *context block* in their description, so
     `Division` (and AI-fit, Themes, Systems, …) round-trip automatically on `import`/`pull`.
   - Issues **authored directly in Jira** have no context block, so `import` labels them **`N/A`** (they all
     pile under one node). To place them properly: edit the `Division` column in `ai-topics.csv` after
     import (then `make build`), or default them all with `import --division "Advice"`.

3. **Good title + a `TLDR;` line.** The Jira **summary** becomes the card title. If the **description**
   starts with `TLDR; a one-line summary`, that line becomes the card's summary and the rest becomes the
   body — the single biggest thing you can do for readable cards.

4. **(Optional) AI-fit / Themes / Systems / Initiative.** `AI-fit` sets the card's legend colour; `Themes`
   and `Systems` feed the WSJF reuse/capability scoring; `Initiative` groups the story in the Initiatives
   lens. These come from the context block (toolkit-created issues) or you fill the CSV columns by hand.

5. **For the Kanban stepper: put it on the board + set priority/flag.** `Stage` is the board column the
   issue's status maps to — so the issue must be on the board (e.g. 6393) in a column named in
   `kanban.stages`. `Swimlane` is which lane query it matches (`Expedite` = `priority = Highest`,
   `Blocked` = flagged). No board position just means no stepper — the card still shows.

**About epics.** The toolkit turns **each imported issue into one opportunity card** — it does **not**
convert Jira **epics** into the map's *Initiatives*. The Initiatives lens is a separate curated list
(`initiatives.csv`), and a story's `Initiative` column is free text. So to reflect epics: put the epic's
name in each story's `Initiative` (context block or CSV column), and/or list your cross-cutting
initiatives in `initiatives.csv`. (Auto-mapping Jira epics → Initiatives isn't built yet — ask if you want it.)

> **Highest-fidelity workflow:** manage the backlog **in the CSV** and use `push` to create the Jira
> issues — they get the embedded context block, so every field round-trips through `pull`/`import`.
> Pure-Jira authoring returns title / description / stage / swimlane automatically; Division / AI-fit /
> Themes / Systems need the context block or a manual CSV edit.

---

## Authoring Jira stories for optimal round-trip (the context block)

The section above lists *which* fields matter. This is *how* to make an issue you author **directly in
Jira** carry them — so `pull` / `import` recover Division, AI-fit, Themes, Systems, Initiative, Status,
Key people and Summary exactly, instead of dropping the issue under `N/A`.

The trick is a **context block**: a horizontal rule followed by a bulleted `Key: value` list at the
**bottom** of the issue **Description**. The toolkit appends this automatically to issues it `push`es
([`build_context_block`](src/jira_common.py:168)) and reads it back on `pull`
([`parse_context_block`](src/jira_common.py:180)) — authoring it by hand just gives a pure-Jira issue the
same fidelity. You never repeat the issue **title** here (it becomes `Opportunity` on its own).

### What the Description should look like

```
TLDR; AI assistant that projects retirement income across super, pension and
investments, with scenario what-ifs.

## Problem
Advisers hand-build retirement projections in spreadsheets — slow and inconsistent.

## Approach
- Pull balances from the platform
- Model drawdown scenarios
- Generate a client-ready summary

———  ← insert a horizontal rule here (type "---" in Jira for a divider)

- Division: Advice
- Initiative: Retirement Planning
- AI-fit: Medium-High
- Status: Endorsed
- Key people: Jane Doe; John Smith
- Systems: MLC Wrap; Salesforce
- Themes: Retirement; Personalisation; Automation
- Summary: AI assistant for retirement income projections with scenario what-ifs.
```

In Jira's editor: write the body, type `---` to insert the divider, then add a normal bulleted list —
one bullet per field. Everything **above** the divider becomes the `Description`; the block below it fills
the metadata columns.

### The rules that make it parse

- **Keys are case-sensitive and literal:** `Division`, `Initiative`, `AI-fit`, `Status`, `Key people`,
  `Systems`, `Themes`, `Summary`. Mind `AI-fit` (hyphen, lowercase *f*) and `Key people` (lowercase *p*).
  An unrecognised key is silently ignored.
- **The separator is `": "`** (colon + space); the value is everything after the first one.
- **The block must sit after a horizontal rule and be the *last* rule + list in the Description** — the
  parser scans backwards for the last divider, so **don't add another divider below it**, and avoid
  horizontal rules inside the body.
- **Omit any field you don't want to manage.** A missing bullet just means `pull` leaves that CSV cell
  untouched — it never blanks it. A minimal block can be as little as `Division` + `AI-fit`.

### Field vocab & formatting

- **Division** — required for the issue to appear on the map (blank-Division rows are dropped). Use the
  exact division name you want it grouped under.
- **AI-fit** — one of `High` / `Medium-High` / `Medium` / `Medium-Low` (sets the card's legend colour;
  anything else falls back to `Medium`).
- **Status** — the funding gate: `Funded` / `Endorsed` / `Prioritised` / `Parked` (drives card sort order
  and the status chip; blank sorts alongside `Prioritised`).
- **Key people / Systems / Themes** — multi-value; separate with **`; `** (semicolon-space), **not**
  commas. A comma *inside* a single value (e.g. `Doe, Jane`) gets over-split downstream.
- **Summary** — a short one-liner. Keep it identical to the body's `TLDR;` line: both feed the card
  summary, but the `TLDR;` line wins for what's displayed, so a mismatch is confusing.

### What does *not* go in the block

- **`Stage` / `Swimlane`** (the Kanban stepper) are **not** part of the context block and are **not read by
  `pull`.** They come only from the issue's **board position** on `import` (status → board column, and the
  swimlane JQL) — see [Kanban progress marker](#kanban-progress-marker-stage--swimlane).
- **`Jira Key` / `Jira URL`** are the link columns, written by `import` / `push` — never hand-encode them.

> **The shortcut:** if you let the toolkit *create* the issue with `make push`, this exact block is
> generated for you, so it round-trips forever with no hand-authoring. Writing the block yourself is only
> for issues that already live in Jira and were **not** created by the toolkit.

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

**Path B — you already have issues in Jira (import the whole project):**
Nominate the project by its key (the `AITR-*` issue prefix ⇒ project `AITR`) and pull the entire
backlog down in one shot — no need to hand-list URLs:

```bash
python3 src/jira_sync.py import --project AITR --csv my-backlog.csv --dry-run   # preview
python3 src/jira_sync.py import --project AITR --csv my-backlog.csv             # write the CSV
```

Foreign issues arrive with `Division = N/A` (override with `--division`, or re-bucket the column
later); issues this toolkit created round-trip their full metadata. See
[`import`](#import--read-a-whole-project-or-jql-into-a-new-csv) for all flags. Afterwards, `pull`
keeps the CSV in sync as those issues change.

*(Prefer to curate by hand? Put one row per issue in a CSV with its `Jira URL` filled — leave
Division/Opportunity/etc. blank — and run `pull --csv my-backlog.csv` to fill them.)*

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
make build CSV=my-backlog.csv OUT="Acme AI Prioritisation.html"
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
views, styling), you edit **one file** and rebuild:

```bash
# edit src/strategy-map.src.html in your editor, then:
make build          # assembles the bundle from source, then renders the HTML
make test           # ALWAYS run the full suite after an app-source edit
```

That's it — there is no separate `apply` step and no stale-bundle footgun. `src/strategy-map.src.html`
is the single source of truth for the app code; `make build` bakes it into the bundle every time.

### How the bundle is assembled (the engine)

The shipped app is a single-file "bundled page" — one HTML carrying the framework runtime, fonts, and
your app code. Rather than checking that 1.5 MB file in and hand-patching it, it's a **generated
artifact** assembled from decomposed source:

- **`src/strategy-map.src.html`** — the editable app source (markup + logic). The *only* thing you edit.
- **`src/engine/skeleton.html`** — the bundle shell + manifest scaffold (~25 KB), with every resource
  blob replaced by an `@@uuid@@` placeholder and the app-source block blanked to `@@TEMPLATE@@`. No app
  code lives here.
- **`src/engine/vendor/<uuid>`** — the vendored engine resources: the framework runtime (gzipped JS) and
  the ~30 woff2 fonts, one file each. Opaque third-party assets you never edit.

`build_bundle.py` reassembles the bundle from those parts and injects your source (`assemble(decompose(bundle))`
is **byte-identical** to the original). `make clean` deletes the generated bundle; `make build`/`make bundle`
rebuild it. The bundle is gitignored — `src/engine/` + `strategy-map.src.html` are what's committed.

> ⚠️ **Always run `make test` after an app-source edit** — `test_regenerate` / `test_lock_app` render the
> reassembled bundle in headless Chromium and catch a broken app. (Mildly flaky on a cold first run because
> of the large bundle; re-run if one times out.)

### One-time engine setup / re-vendoring

`src/engine/` is committed, so a fresh clone builds with no extra steps. You only touch it when the
**upstream engine** (runtime or fonts) changes — then re-derive it from a good bundle:

```bash
make engine-extract      # bundle -> src/engine/skeleton.html + src/engine/vendor/*  (decompose_bundle.py)
```

### Supporting tools

- `decompose_bundle.py` / `build_bundle.py` — split a bundle into `src/engine/` ⇄ reassemble it from source.
- `apply_source.py` — low-level: patch the app source into an existing bundle in place (`--extract` to pull
  it back out). Used internally by `build_bundle.py`; you rarely call it directly now.
- `bundle_resources.py` — copy a resource (font/JS) from one bundle's manifest into another, or remove one by uuid.

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
division's cards fan out by **funding‑gate status** (`Funded` ▸ `Endorsed` ▸ `Prioritised` ▸
`Parked`) and then WSJF‑desc within each band, each card carrying a status chip and a
`WSJF x.x · #rank` badge (**Parked** cards are dimmed). A **◆ Priority heat** toggle tints division
nodes by their share of the top‑25, and **View in Priority →** on a selected division opens the
Priority tab scoped to it (a clearable chip restores the full backlog).

**Initiatives lens & drill‑down.** `Division` and `Initiative` are independent axes — a story
belongs to one division and is one instantiation of one initiative, and the same initiative
(e.g. *Knowledge Bases*, *CGT Calculation*) recurs across divisions. In the **Initiatives** lens,
selecting an initiative opens a drill‑down of its story‑instances **grouped by the division they
live in**, each group headed by the division's colour and count, each story status‑then‑WSJF
sorted and showing its status chip; clicking a story opens that story's detail. The
initiative↔division spread is derived from the stories, not stored.

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
| `Insignia AI Strategy Map - Jira linked.html` | The app bundle — **generated** from `src/engine/` + `strategy-map.src.html` by `make build` (gitignored) |
| `src/strategy-map.src.html` | **The editable app source** — the single file you edit to change the app |
| `src/engine/skeleton.html` | Bundle shell + manifest scaffold (placeholders, no app code) — committed |
| `src/engine/vendor/` | Vendored engine resources (framework runtime + woff2 fonts), one file each — committed |
| `Insignia AI Strategy Map - locked.html` | View‑only shipped bundle (generated, gitignored) |
| `Insignia AI Strategy Map - regenerated.html` | `regenerate` output (generated, gitignored) |
| `app/index.html` | Deployed page — `make deploy` copies the regenerated HTML here (gitignored) |
| `Makefile` | Convenience targets (`make help` lists them) |
| `src/jira_sync.py` | CLI: `push` / `pull` / `import` |
| `src/jira_common.py` | Shared: `.env` loader, CSV I/O, markdown⇄ADF, context‑block round‑trip, labels, Jira client + preflight |
| `src/regenerate_html.py` | Rebuild the whole HTML from stories CSV + `initiatives.csv` + `settings.yaml` + `people.csv` |
| `src/settings_common.py` | Settings load, division derivation, settings + people overlay |
| `src/export_tabs.py` | Seed `initiatives.csv` / `settings.yaml` / `people.csv` from the app's current content |
| `src/lock_app.py` | Bake the view‑only lock guard into the app source → locked bundle |
| `src/build_bundle.py` | **Assemble** the bundle from `src/engine/` + `strategy-map.src.html` (used by `make build`) |
| `src/decompose_bundle.py` | Maintenance: **split** a bundle into `src/engine/` (skeleton + vendored resources) |
| `src/apply_source.py` | Low‑level: inject the app source into a bundle in place — `make apply` / `make extract` (used internally by `build_bundle.py`) |
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
- **Kanban stepper not showing on cards** — the marker needs all three: (1) the CSV has populated
  `Stage`/`Swimlane` columns, (2) `settings.yaml` has the `kanban:` block, (3) you rebuilt after
  syncing `src/`. Usually it's (1): the CSV was imported *before* the feature. Re-import with the
  board, then rebuild:

  ```bash
  python3 src/jira_sync.py import --project AITR --board 6393 --csv ai-topics.csv
  make build CSV=ai-topics.csv OUT="AITR Strategy Map.html"
  ```

  Still blank? Check which of the three is missing:

  ```bash
  python3 -c "import csv; r=list(csv.DictReader(open('ai-topics.csv'))); print('columns:', list(r[0].keys())); print('stages:', sorted(set(x.get('Stage','') for x in r))); print('lanes:', sorted(set(x.get('Swimlane','') for x in r)))"
  grep -c '^kanban:' settings.yaml            # want 1
  grep -c 'stageMarker' src/strategy-map.src.html   # want >0
  ```

  If `stages` is `['']` the CSV is stale (re-import); if it's raw statuses like `['To Do']` instead of
  your column names, the status→column mapping missed the board (pass `--board`, or align
  `kanban.stages` to the names `import` printed).
