# tests/test_bundle_resources.py — verify copy_resource/remove_resource
# against the real repo-root bundles.
import json
import re

import bundle_resources as br

MANI_RE = re.compile(r'<script type="__bundler/manifest">(.*?)</script>', re.S)

MAIN = "Insignia AI Strategy Map - Jira linked.html"
WSJF = "WSJF Studio v2.html"


def _manifest(html):
    m = MANI_RE.search(html)
    assert m, "manifest block not found"
    return json.loads(m.group(1).strip())


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _first_uuid_with_mime(manifest, mime):
    for uuid, entry in manifest.items():
        if entry.get("mime") == mime:
            return uuid
    raise AssertionError(f"no manifest entry with mime={mime!r}")


def test_copy_resource_adds_font_entry_from_wsjf_into_main():
    # Hermetic: uses an explicit, guaranteed-novel new_uuid so the result
    # doesn't depend on whether MAIN already contains this WSJF font uuid
    # (it does, permanently, once import_wsjf_fonts.py has run — see the
    # idempotent-overwrite test below for that property).
    main_html = _read(MAIN)
    wsjf_html = _read(WSJF)

    main_manifest = _manifest(main_html)
    wsjf_manifest = _manifest(wsjf_html)
    src_uuid = _first_uuid_with_mime(wsjf_manifest, "font/woff2")

    novel_uuid = "wsjf-copytest-0001"
    assert novel_uuid not in main_manifest, "test fixture uuid unexpectedly already present"

    new_html, new_uuid = br.copy_resource(main_html, wsjf_html, src_uuid, new_uuid=novel_uuid)

    new_manifest = _manifest(new_html)
    assert new_uuid == novel_uuid
    assert new_uuid in new_manifest
    assert len(new_manifest) == len(main_manifest) + 1
    assert new_manifest[new_uuid] == wsjf_manifest[src_uuid]


def test_copy_resource_default_new_uuid_is_idempotent_overwrite():
    # Documents the property import_wsjf_fonts.py relies on: copying with
    # the default new_uuid (= src_uuid) is safe to re-run — the second call
    # overwrites the same key instead of growing the manifest.
    main_html = _read(MAIN)
    wsjf_html = _read(WSJF)

    wsjf_manifest = _manifest(wsjf_html)
    src_uuid = _first_uuid_with_mime(wsjf_manifest, "font/woff2")

    once_html, once_uuid = br.copy_resource(main_html, wsjf_html, src_uuid)
    once_manifest = _manifest(once_html)

    twice_html, twice_uuid = br.copy_resource(once_html, wsjf_html, src_uuid)
    twice_manifest = _manifest(twice_html)

    assert once_uuid == twice_uuid == src_uuid
    assert len(twice_manifest) == len(once_manifest)
    assert twice_manifest[src_uuid] == wsjf_manifest[src_uuid]


def test_remove_resource_drops_csv_entry_from_wsjf():
    wsjf_html = _read(WSJF)

    before_manifest = _manifest(wsjf_html)
    victim_uuid = _first_uuid_with_mime(before_manifest, "text/csv")

    new_html = br.remove_resource(wsjf_html, victim_uuid)

    after_manifest = _manifest(new_html)
    assert victim_uuid not in after_manifest
    assert len(after_manifest) == len(before_manifest) - 1
