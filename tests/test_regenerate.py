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

    import yaml
    settings_p = tmp_path / "settings.yaml"
    company = "ZZCOMPANY_regen"
    yaml.safe_dump({"header": {"company": company}}, open(settings_p, "w"))
    init_p = tmp_path / "initiatives.csv"
    jc.write_csv(init_p, [], fieldnames=["#", "Initiative", "Capability",
        "Effort", "Value", "Quadrant", "Divisions impacted"])

    people_p = tmp_path / "people.csv"
    person = "ZZPERSON_regen"
    jc.write_csv(people_p, [{"Division": "D", "Name": person,
                             "Role": "Tester", "Relevance": "sentinel"}],
                 fieldnames=["Division", "Name", "Role", "Relevance"])

    out = tmp_path / "out.html"
    regenerate_html.regenerate(str(src_csv), str(HTML), str(out), headed=False,
                               initiatives_path=str(init_p),
                               settings_path=str(settings_p),
                               divisions_out=str(tmp_path / "divisions.csv"),
                               people_path=str(people_p))
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
        # textContent (not innerText) — the header applies CSS text-transform:
        # uppercase to the company name, which innerText would bake in and
        # break an exact-string match against the settings value.
        body = pg.evaluate("() => document.body.textContent")
        assert company in body, "settings header.company not in regenerated HTML"

        # People live in editable <input> fields inside a division's detail
        # row (Data > Divisions > "Edit details") in the *unlocked* app —
        # but the shipped output is now the LOCKED bundle, which hides the
        # "Edit details" pencil and flattens inputs, so that navigation path
        # no longer works. The app only writes to localStorage on the first
        # edit (see persist()/loadData() in the bundle); a freshly opened
        # download instead boots straight from the embedded
        # window.WORKSHOP_DATA snapshot, so read the person from there
        # instead — a check that's meaningful either way and doesn't depend
        # on mutation UI being present.
        person_present = pg.evaluate(
            "(s) => JSON.stringify(window.WORKSHOP_DATA.departments)"
            ".includes(s)", person)
        assert person_present, "people.csv person not in regenerated HTML"

        # The shipped output is the LOCKED bundle: no upload/edit/add/delete
        # controls, but Export CSV must still work.
        locked = pg.evaluate("""() => {
          const vis = el => el.offsetParent !== null && !el.hasAttribute('data-lock-hide');
          const btn = t => [...document.querySelectorAll('button')].filter(b=>t(b)&&vis(b)).length;
          return {
            upload: [...document.querySelectorAll('label')].filter(l=>/Upload CSV/i.test(l.textContent)&&vis(l)).length,
            pencils: btn(b=>b.getAttribute('title')==='Edit details'),
            adds: btn(b=>/^\\+\\s*Add/.test((b.textContent||'').trim())),
            dels: btn(b=>(b.textContent||'').trim()==='\\u00d7'),
            exportPresent: [...document.querySelectorAll('button,a')].some(e=>/Export CSV/i.test(e.textContent||'')),
          };
        }""")
        assert locked["upload"]==0 and locked["pencils"]==0 and locked["adds"]==0 and locked["dels"]==0
        assert locked["exportPresent"] is True
        b.close()
    assert present, "sentinel from CSV not found in regenerated HTML"
