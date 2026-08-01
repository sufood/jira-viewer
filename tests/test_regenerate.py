"""Smoke test for regenerate_html.py.

Runs the real browser flow against the real app bundle with a tiny 1-row CSV,
and confirms the regenerated HTML actually reflects the CSV (a sentinel value
imported through the app is present in the output). Skipped automatically when
the source HTML, Playwright, or a Chromium build isn't available, so the core
unit suite stays fast and dependency-light.
"""

import pathlib
import re

import pytest

import jira_common as jc

HTML = pathlib.Path(__file__).resolve().parent.parent / \
    "Insignia AI Strategy Map - Jira linked.html"


def _chromium_available():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as pw:
            pw.chromium.launch(headless=True).close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not HTML.exists() or not _chromium_available(),
    reason="source HTML or Playwright/Chromium not available",
)


def test_regenerate_reflects_csv(tmp_path):
    import regenerate_html

    sentinel = "ZZQXSENTINEL_pytest_regen"
    src_csv = tmp_path / "in.csv"
    row = {c: "" for c in jc.COLUMNS}
    row.update({"#": "1", "Division": "D", "Opportunity": sentinel,
                "AI-fit": "High", "Key people": "P", "Systems": "S",
                "Themes": "T", "Summary": "s", "Description": "body"})
    jc.write_csv(src_csv, [row])

    out = tmp_path / "out.html"
    regenerate_html.regenerate(str(src_csv), str(HTML), str(out), headed=False)
    assert out.exists() and out.stat().st_size > 100_000

    # Confirm the imported sentinel round-tripped into the regenerated app.
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_page()
        pg.goto(out.resolve().as_uri())
        pg.get_by_role("button", name=re.compile(r"^Data$")).wait_for(timeout=30_000)
        sub = pg.get_by_role("button", name=re.compile("Division stories"))
        for _ in range(5):
            pg.get_by_role("button", name=re.compile(r"^Data$")).click()
            try:
                sub.wait_for(state="visible", timeout=4000)
                break
            except Exception:
                continue
        sub.click()
        pg.wait_for_timeout(1000)
        present = pg.evaluate(
            "(s) => [...document.querySelectorAll('input,textarea,td,div')]"
            ".some(e => (e.value||e.textContent||'').includes(s))", sentinel)
        b.close()
    assert present, "sentinel from CSV not found in regenerated HTML"
