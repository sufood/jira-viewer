"""Browser validation for lock_app.py.

Key finding from probing the real app: __PRISTINE_HTML is a dormant snapshot
— it is NOT what renders when you open a bundle file directly (the live page
streams its template from other bundle resources). It only becomes real,
executing markup inside the file produced by clicking "Download standalone
HTML" (downloadPage() rebuilds a static page from __PRISTINE_HTML + the
current data + window.__DATA_READONLY=true). So the lock guard we bake into
__PRISTINE_HTML only manifests in that downloaded artifact — this test
therefore builds the locked bundle, opens it (still the original, unlocked,
live app — expected), triggers "Download standalone HTML", and asserts
against the DOWNLOADED file.

Skipped automatically when the source HTML, Playwright, or a Chromium build
isn't available.
"""

import pathlib
import re

import pytest

SRC = pathlib.Path(__file__).resolve().parent.parent / \
    "Insignia AI Strategy Map - Jira linked.html"

DATA_TAB = re.compile(r"^Data$")
SAVE_BUTTON = re.compile(r"Download standalone HTML")


def _chromium():
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


pytestmark = pytest.mark.skipif(not SRC.exists() or not _chromium(),
                                reason="source HTML or Chromium unavailable")


def _collect_lock_counts(page):
    """Evaluate the Data-tab lock-state counters on the current page."""
    return page.evaluate("""() => {
      const vis = el => el.offsetParent !== null &&
        !el.hasAttribute('data-lock-hide');
      const btn = t => [...document.querySelectorAll('button')]
        .filter(b => t(b) && vis(b)).length;
      return {
        upload: [...document.querySelectorAll('label')]
          .filter(l => /Upload CSV/i.test(l.textContent) && vis(l)).length,
        pencils: btn(b => b.getAttribute('title') === 'Edit details'),
        adds: btn(b => (b.textContent || '').trim().indexOf('+ Add') === 0),
        dels: btn(b => (b.textContent || '').trim() === '\\u00d7'),
        downloadStandalone: btn(b =>
          (b.textContent || '').indexOf('Download standalone') !== -1),
        liveInputs: [...document.querySelectorAll('input:not([type=file]),textarea')]
          .filter(i => vis(i) && !i.classList.contains('__lock-static')).length,
        exportPresent: [...document.querySelectorAll('button,a')]
          .some(e => /Export CSV/i.test(e.textContent || '')),
        renders: !!document.querySelector('input,td,div'),
      };
    }""")


def _goto_data_tab(page):
    page.get_by_role("button", name=DATA_TAB).wait_for(timeout=30_000)
    sub = page.get_by_role("button", name=re.compile("Divisions ·"))
    for _ in range(8):
        page.get_by_role("button", name=DATA_TAB).click()
        try:
            sub.wait_for(state="visible", timeout=5_000)
            break
        except Exception:
            continue
    sub.click()
    page.wait_for_timeout(800)


def test_locked_bundle_has_no_mutation_controls_after_download(tmp_path):
    import lock_app
    from playwright.sync_api import sync_playwright

    locked = tmp_path / "locked.html"
    locked.write_text(lock_app.build_locked(SRC.read_text(encoding="utf-8")),
                      encoding="utf-8")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(accept_downloads=True)
        page.goto(locked.resolve().as_uri())
        page.get_by_role("button", name=DATA_TAB).wait_for(timeout=30_000)
        page.wait_for_timeout(2500)

        # Trigger the app's own "Download standalone HTML" — this is what
        # rebuilds a page from the (now-guarded) __PRISTINE_HTML. The
        # download event is occasionally flaky under load, so retry.
        downloaded = tmp_path / "downloaded.html"
        dl_value = None
        last_err = None
        for _ in range(4):
            try:
                with page.expect_download(timeout=15_000) as dl_info:
                    page.get_by_role("button", name=SAVE_BUTTON).click()
                dl_value = dl_info.value
                break
            except Exception as e:  # pragma: no cover - timing flake retry
                last_err = e
                page.wait_for_timeout(1000)
        if dl_value is None:
            raise last_err
        dl_value.save_as(str(downloaded))
        browser.close()

    assert downloaded.stat().st_size > 100_000

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(downloaded.resolve().as_uri())
        _goto_data_tab(page)
        counts = _collect_lock_counts(page)

        # Export must actually work: it should trigger a real download whose
        # content reflects the active sub-tab (Divisions here).
        with page.expect_download(timeout=10_000) as export_dl:
            page.get_by_role("button", name=re.compile("Export CSV")).click()
        export_path = tmp_path / "export.csv"
        export_dl.value.save_as(str(export_path))
        browser.close()

    assert counts["upload"] == 0
    assert counts["pencils"] == 0
    assert counts["adds"] == 0
    assert counts["dels"] == 0
    assert counts["downloadStandalone"] == 0  # no re-download-to-broken-file button
    assert counts["liveInputs"] == 0        # all data inputs flattened to static
    assert counts["exportPresent"] is True
    assert counts["renders"] is True

    export_text = export_path.read_text(encoding="utf-8-sig")
    assert export_text.splitlines()[0].startswith('"Division"')
    assert len(export_text.splitlines()) > 1   # header + at least one data row


def test_build_locked_is_idempotent():
    import lock_app
    import bundle_common as bc

    src = SRC.read_text(encoding="utf-8")
    once = lock_app.build_locked(src)
    twice = lock_app.build_locked(once)

    uuid = bc.find_resource_with(once, "__PRISTINE_HTML")
    text_once = bc.get_resource_text(once, uuid)
    text_twice = bc.get_resource_text(twice, uuid)
    assert text_once == text_twice
    assert text_once.count("__lock_script") == 1
