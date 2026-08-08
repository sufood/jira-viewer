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
    main_html = _read(MAIN)
    wsjf_html = _read(WSJF)

    main_manifest = _manifest(main_html)
    wsjf_manifest = _manifest(wsjf_html)
    src_uuid = _first_uuid_with_mime(wsjf_manifest, "font/woff2")

    new_html, new_uuid = br.copy_resource(main_html, wsjf_html, src_uuid)

    new_manifest = _manifest(new_html)
    assert new_uuid in new_manifest
    assert len(new_manifest) == len(main_manifest) + 1
    assert new_manifest[new_uuid] == wsjf_manifest[src_uuid]


def test_remove_resource_drops_csv_entry_from_wsjf():
    wsjf_html = _read(WSJF)

    before_manifest = _manifest(wsjf_html)
    victim_uuid = _first_uuid_with_mime(before_manifest, "text/csv")

    new_html = br.remove_resource(wsjf_html, victim_uuid)

    after_manifest = _manifest(new_html)
    assert victim_uuid not in after_manifest
    assert len(after_manifest) == len(before_manifest) - 1
