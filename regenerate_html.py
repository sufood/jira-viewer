#!/usr/bin/env python3
"""Regenerate the standalone HTML from the CSV by driving the app's own
CSV-import + "Download standalone HTML" in headless Chromium.

The app's data is gzip+base64-compressed inside the HTML bundle and lives in
localStorage at runtime — there is no clean text-injection point, so we reuse
the app's real serializer instead of editing the bundle.

This is a TWO-STAGE build so the shipped output is the locked, view-only app:

  Stage 1 (editable copy): open the editable app bundle, import the 3 CSVs
  through the app's own Upload CSV, then overlay settings/people onto the
  resulting data object in Python (the same merges as before). This stage
  never downloads — its output is just the in-memory data dict.

  Stage 2 (ship): open the LOCKED bundle (built once from the editable
  bundle via lock_app.build_locked, then reused), inject the Stage-1 data
  object into its localStorage, reload, and click "Download standalone
  HTML". Because the lock guard only takes effect in a *downloaded*
  artifact rebuilt from __PRISTINE_HTML, the download from the locked
  bundle is itself locked — no upload/edit/add/delete controls, Export CSV
  intact.

    python regenerate_html.py                     # defaults below
    python regenerate_html.py --headed            # watch it run
    python regenerate_html.py --csv X --html Y --out Z

Requires: pip install playwright && python -m playwright install chromium
"""

import argparse
import pathlib
import re
import sys
import json

import jira_common as jc
import lock_app
import settings_common as sc

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

DEFAULT_CSV = "insignia-division-stories-jira-linked.csv"
DEFAULT_HTML = "Insignia AI Strategy Map - Jira linked.html"
DEFAULT_OUT = "Insignia AI Strategy Map - regenerated.html"
DEFAULT_LOCKED_HTML = "Insignia AI Strategy Map - locked.html"

DATA_KEY = "insignia_ai_strategy_map_v2"

# Selectors discovered against the real app DOM:
#   - the Data top tab
#   - the "Division stories" sub-tab (our CSV's target dataset)
#   - a single hidden <input type=file accept=".csv,text/csv"> (Upload CSV label)
#   - the "Download standalone HTML" button (embeds current edits)
DATA_TAB = re.compile(r"^Data$")
SUBTAB_DIVISION_STORIES = re.compile(r"Division stories")
FILE_INPUT = 'input[type="file"]'
SAVE_BUTTON = re.compile(r"Download standalone HTML")


def _build_data(csv_path, html_path, out_path, headed,
                initiatives_path, settings_path, divisions_out, people_path):
    """Stage 1: drive the editable app bundle through the CSV imports, then
    overlay settings/people in Python. Returns the merged data dict. Never
    reloads or downloads."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        page = browser.new_page(accept_downloads=True)
        page.goto(html_path.as_uri())

        # The bundle unpacks then React renders — wait for the tabs, not
        # networkidle (fonts may be fetched from the network and never idle).
        try:
            page.get_by_role("button", name=DATA_TAB).wait_for(timeout=30_000)
        except PWTimeout:
            page.screenshot(path=str(out_path.with_suffix(".load-error.png")))
            browser.close()
            sys.exit("ERROR: app never rendered its tabs (see .load-error.png). "
                     "The HTML may not be the expected app bundle.")

        # The tabs render before React finishes attaching click handlers, so a
        # click fired too early is silently dropped. Give hydration a moment,
        # then retry the Data click until the sub-tabs actually mount.
        page.wait_for_timeout(1500)
        substab = page.get_by_role("button", name=SUBTAB_DIVISION_STORIES)
        for _ in range(10):
            page.get_by_role("button", name=DATA_TAB).click()
            try:
                substab.wait_for(state="visible", timeout=6000)
                break
            except PWTimeout:
                continue
        else:
            page.screenshot(path=str(out_path.with_suffix(".tab-error.png")))
            browser.close()
            sys.exit("ERROR: Data tab never revealed its sub-tabs "
                     "(see .tab-error.png).")

        # Derive divisions.csv from the stories CSV + settings (A2/A3).
        if not pathlib.Path(settings_path).exists():
            print(f"  notice: {settings_path} missing; settings overlay skipped")
        settings = sc.load_settings(settings_path)
        div_rows, unmatched = sc.derive_divisions(jc.read_csv(str(csv_path)),
                                                  settings)
        for name in unmatched:
            print(f"  notice: settings division {name!r} has no stories; ignored")
        jc.write_csv(divisions_out, div_rows, fieldnames=sc.DIVISION_COLUMNS)

        # Import the three tabs via the app's own Upload CSV. Order matters:
        # stories -> divisions (division metadata authoritative) -> initiatives.
        imports = [("Division stories ·", str(csv_path)),
                   ("Divisions ·", str(pathlib.Path(divisions_out).resolve())),
                   ("Initiatives ·", initiatives_path)]
        for subtab, path in imports:
            if not pathlib.Path(path).exists():
                print(f"  notice: {path} missing; skipping "
                      f"{subtab.strip(' ·')} import")
                continue
            page.get_by_role("button", name=re.compile(re.escape(subtab))).click()
            page.wait_for_timeout(600)
            page.set_input_files(FILE_INPUT, str(pathlib.Path(path).resolve()))
            page.wait_for_timeout(1800)

        # Overlay settings (header/hub/legend) and people onto the app's data
        # object in Python — neither has a CSV import path. A missing
        # people.csv leaves existing people intact; an empty-but-present one
        # is authoritative (clears people).
        people_rows = (jc.read_csv(people_path)
                       if pathlib.Path(people_path).exists() else None)
        if people_rows is None:
            print(f"  notice: {people_path} missing; division people left as-is")

        raw = page.evaluate(f"() => localStorage.getItem('{DATA_KEY}')")
        if not raw:
            page.screenshot(path=str(out_path.with_suffix(".data-error.png")))
            browser.close()
            sys.exit("ERROR: no app data in localStorage after import "
                     "(see .data-error.png) — cannot ship without data.")

        data = json.loads(raw)
        if settings:
            sc.merge_settings_into_data(data, settings)
        if people_rows is not None:   # [] is authoritative: clears people
            _, unmatched = sc.apply_people(data, people_rows)
            for name in unmatched:
                print(f"  notice: people.csv division {name!r} "
                      f"matches no division; ignored")

        browser.close()
    return data


def _ship(data, locked_html_path, out_path, headed):
    """Stage 2: open the LOCKED bundle, inject the Stage-1 data object, and
    download — the download from a locked bundle is itself locked."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        page = browser.new_page(accept_downloads=True)
        page.goto(locked_html_path.as_uri())

        try:
            page.get_by_role("button", name=DATA_TAB).wait_for(timeout=30_000)
        except PWTimeout:
            page.screenshot(path=str(out_path.with_suffix(".load-error.png")))
            browser.close()
            sys.exit("ERROR: locked app never rendered its tabs "
                     "(see .load-error.png).")
        page.wait_for_timeout(1500)  # settle

        page.evaluate(
            f"(v) => localStorage.setItem('{DATA_KEY}', v)",
            json.dumps(data, ensure_ascii=False))
        page.reload()
        page.get_by_role("button", name=DATA_TAB).wait_for(timeout=30_000)
        page.wait_for_timeout(2500)  # settle — the download path is timing-flaky

        # Trigger the app's own serializer and capture the download to a
        # temp file first, so a truncated download never clobbers a good
        # --out. The download can be flaky right after a reload, so retry.
        part = out_path.with_suffix(out_path.suffix + ".part")
        last_err = None
        for _ in range(4):
            page.wait_for_timeout(2500)
            try:
                with page.expect_download(timeout=20_000) as dl_info:
                    page.get_by_role("button", name=SAVE_BUTTON).click()
                dl_info.value.save_as(str(part))
                last_err = None
                break
            except PWTimeout as e:
                last_err = e
                continue

        if last_err is not None:
            page.screenshot(path=str(out_path.with_suffix(".save-error.png")))
            browser.close()
            sys.exit("ERROR: no download after clicking Save (see .save-error.png).")
        browser.close()

    size = part.stat().st_size if part.exists() else 0
    if size < 100_000:
        if part.exists():
            part.unlink()
        sys.exit(f"ERROR: download was only {size} bytes — regeneration "
                 f"likely failed; left {out_path.name} unchanged.")
    part.replace(out_path)               # atomic promote only after validation
    print(f"Regenerated {out_path} ({size:,} bytes)")


def regenerate(csv_path, html_path, out_path, headed,
               initiatives_path="initiatives.csv",
               settings_path="settings.yaml",
               divisions_out="divisions.csv",
               people_path="people.csv",
               locked_html_path=DEFAULT_LOCKED_HTML):
    csv_path = pathlib.Path(csv_path).resolve()
    html_path = pathlib.Path(html_path).resolve()
    out_path = pathlib.Path(out_path).resolve()
    locked_html_path = pathlib.Path(locked_html_path).resolve()
    for p in (csv_path, html_path):
        if not p.exists():
            sys.exit(f"Missing input: {p}")

    # Stage 1: build the data object from an editable copy of the app.
    data = _build_data(csv_path, html_path, out_path, headed,
                       initiatives_path, settings_path, divisions_out,
                       people_path)

    # Build the locked bundle once, then reuse it on every subsequent run.
    if not locked_html_path.exists():
        print(f"  notice: {locked_html_path} missing; building it from "
              f"{html_path}")
        locked_html_path.write_text(
            lock_app.build_locked(html_path.read_text(encoding="utf-8")),
            encoding="utf-8")

    # Stage 2: ship — inject the data into the locked bundle and download.
    _ship(data, locked_html_path, out_path, headed)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default=DEFAULT_CSV)
    ap.add_argument("--html", default=DEFAULT_HTML)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--initiatives", default="initiatives.csv")
    ap.add_argument("--settings", default="settings.yaml")
    ap.add_argument("--divisions-out", default="divisions.csv")
    ap.add_argument("--people", default="people.csv")
    ap.add_argument("--locked-html", default=DEFAULT_LOCKED_HTML)
    args = ap.parse_args()
    regenerate(args.csv, args.html, args.out, args.headed,
               initiatives_path=args.initiatives, settings_path=args.settings,
               divisions_out=args.divisions_out, people_path=args.people,
               locked_html_path=args.locked_html)


if __name__ == "__main__":
    main()
