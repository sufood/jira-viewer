#!/usr/bin/env python3
"""Regenerate the standalone HTML from the CSV by driving the app's own
CSV-import + "Download standalone HTML" in headless Chromium.

The app's data is gzip+base64-compressed inside the HTML bundle and lives in
localStorage at runtime — there is no clean text-injection point, so we reuse
the app's real serializer instead of editing the bundle.

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
import settings_common as sc

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

DEFAULT_CSV = "insignia-division-stories-jira-linked.csv"
DEFAULT_HTML = "Insignia AI Strategy Map - Jira linked.html"
DEFAULT_OUT = "Insignia AI Strategy Map - regenerated.html"

# Selectors discovered against the real app DOM:
#   - the Data top tab
#   - the "Division stories" sub-tab (our CSV's target dataset)
#   - a single hidden <input type=file accept=".csv,text/csv"> (Upload CSV label)
#   - the "Download standalone HTML" button (embeds current edits)
DATA_TAB = re.compile(r"^Data$")
SUBTAB_DIVISION_STORIES = re.compile(r"Division stories")
FILE_INPUT = 'input[type="file"]'
SAVE_BUTTON = re.compile(r"Download standalone HTML")


def regenerate(csv_path, html_path, out_path, headed,
               initiatives_path="initiatives.csv",
               settings_path="settings.yaml",
               divisions_out="divisions.csv"):
    csv_path = pathlib.Path(csv_path).resolve()
    html_path = pathlib.Path(html_path).resolve()
    out_path = pathlib.Path(out_path).resolve()
    for p in (csv_path, html_path):
        if not p.exists():
            sys.exit(f"Missing input: {p}")

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

        # Overlay settings (header/hub/legend) into the app's data object, which
        # has no CSV import path, then reload so the app boots the merged state.
        if settings:
            raw = page.evaluate(
                "() => localStorage.getItem('insignia_ai_strategy_map_v2')")
            if raw:
                data = sc.merge_settings_into_data(json.loads(raw), settings)
                page.evaluate(
                    "(v) => localStorage.setItem("
                    "'insignia_ai_strategy_map_v2', v)",
                    json.dumps(data, ensure_ascii=False))
                page.reload()
                page.get_by_role("button", name=DATA_TAB).wait_for(timeout=30_000)
                page.wait_for_timeout(1000)
            else:
                print("  notice: no app data in localStorage after import; "
                      "settings overlay skipped")

        # Trigger the app's own serializer and capture the download to a
        # temp file first, so a truncated download never clobbers a good --out.
        part = out_path.with_suffix(out_path.suffix + ".part")
        try:
            with page.expect_download(timeout=30_000) as dl_info:
                page.get_by_role("button", name=SAVE_BUTTON).click()
            dl_info.value.save_as(str(part))
        except PWTimeout:
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
    args = ap.parse_args()
    regenerate(args.csv, args.html, args.out, args.headed,
               initiatives_path=args.initiatives, settings_path=args.settings,
               divisions_out=args.divisions_out)


if __name__ == "__main__":
    main()
