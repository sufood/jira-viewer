#!/usr/bin/env python3
"""Export the app's current tabs to editable seed files, using its own Export CSV.

    python export_tabs.py                       # writes initiatives.csv, divisions-current.csv, settings.yaml
    python export_tabs.py --html X --headed

Produces the starter files you then hand-edit. `divisions-current.csv` is a
reference dump of the app's current Divisions tab (the live regenerate derives
its own divisions.csv from the stories CSV — this is just for seeding settings).
"""

import argparse
import json
import pathlib
import re
import sys

import yaml
from playwright.sync_api import sync_playwright

import jira_common as jc
import settings_common as sc

DEFAULT_HTML = "Insignia AI Strategy Map - Jira linked.html"


def _export_tab(page, subtab_label, out_path):
    page.get_by_role("button", name=re.compile(re.escape(subtab_label))).click()
    page.wait_for_timeout(600)
    with page.expect_download(timeout=30_000) as dl:
        page.get_by_role("button", name=re.compile("Export CSV")).click()
    dl.value.save_as(str(out_path))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--html", default=DEFAULT_HTML)
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    html = pathlib.Path(args.html).resolve()
    if not html.exists():
        sys.exit(f"Missing HTML: {html}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed)
        page = browser.new_page(accept_downloads=True)
        page.goto(html.as_uri())
        page.get_by_role("button", name=re.compile(r"^Data$")).wait_for(timeout=30_000)
        page.wait_for_timeout(1500)
        for _ in range(10):
            page.get_by_role("button", name=re.compile(r"^Data$")).click()
            try:
                page.get_by_role("button",
                                 name=re.compile("Divisions ·")).wait_for(
                                     state="visible", timeout=6000)
                break
            except Exception:
                continue
        _export_tab(page, "Initiatives ·", "initiatives.csv")
        _export_tab(page, "Divisions ·", "divisions-current.csv")

        # People have no Export-CSV tab. Force a save by re-importing the app's
        # own divisions export (identity — doesn't touch people), then read
        # departments[].people out of localStorage.
        page.get_by_role("button", name=re.compile("Divisions ·")).click()
        page.wait_for_timeout(500)
        page.set_input_files(
            'input[type="file"]',
            str(pathlib.Path("divisions-current.csv").resolve()))
        page.wait_for_timeout(1800)
        raw = page.evaluate(
            "() => localStorage.getItem('insignia_ai_strategy_map_v2')")
        browser.close()

    div_rows = jc.read_csv("divisions-current.csv")
    with open("settings.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(sc.build_starter_settings(div_rows), f,
                       sort_keys=False, allow_unicode=True, width=100)

    # Don't clobber a hand-edited people.csv with an empty file if the forced
    # save didn't land (no app data read back) — abort loudly instead.
    if not raw:
        sys.exit("ERROR: could not read app data after import; people.csv NOT "
                 "written (left any existing file untouched). Re-run, or use "
                 "--headed to watch.")
    people_rows = []
    for dep in json.loads(raw).get("departments", []):
        for p in dep.get("people", []):
            people_rows.append({"Division": dep.get("name", ""),
                                "Name": p.get("name", ""),
                                "Role": p.get("role", ""),
                                "Relevance": p.get("relevance", "")})
    jc.write_csv("people.csv", people_rows, fieldnames=sc.PEOPLE_COLUMNS)
    print("Wrote initiatives.csv, divisions-current.csv, settings.yaml, people.csv")


if __name__ == "__main__":
    main()
