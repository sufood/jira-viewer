# tests/test_bundle_resources.py — verify copy_resource/remove_resource on
# synthetic in-memory bundles (no dependency on any real bundle file).
import json
import re

import bundle_resources as br

MANI_RE = re.compile(r'<script type="__bundler/manifest">(.*?)</script>', re.S)


def _bundle(manifest):
    return ('<!doctype html><html><head></head><body>'
            '<script type="__bundler/manifest">'
            + json.dumps(manifest, separators=(",", ":"))
            + '</script></body></html>')


def _manifest(html):
    m = MANI_RE.search(html)
    assert m, "manifest block not found"
    return json.loads(m.group(1).strip())


def _entry(mime, data):
    return {"mime": mime, "compressed": False, "data": data}


def test_copy_resource_adds_entry_with_novel_uuid():
    src = _bundle({"font-a": _entry("font/woff2", "AAA="),
                   "csv-a": _entry("text/csv", "Q1NW")})
    dst = _bundle({"x": _entry("text/javascript", "Zm9v")})
    dst_manifest = _manifest(dst)

    new_html, new_uuid = br.copy_resource(dst, src, "font-a", new_uuid="copied-1")
    new_manifest = _manifest(new_html)

    assert new_uuid == "copied-1"
    assert new_uuid in new_manifest
    assert len(new_manifest) == len(dst_manifest) + 1
    assert new_manifest[new_uuid] == _manifest(src)["font-a"]


def test_copy_resource_default_new_uuid_is_idempotent_overwrite():
    # Copying with the default new_uuid (= src_uuid) is safe to re-run: the
    # second call overwrites the same key instead of growing the manifest.
    src = _bundle({"font-a": _entry("font/woff2", "AAA=")})
    dst = _bundle({"x": _entry("text/javascript", "Zm9v")})

    once_html, once_uuid = br.copy_resource(dst, src, "font-a")
    twice_html, twice_uuid = br.copy_resource(once_html, src, "font-a")

    assert once_uuid == twice_uuid == "font-a"
    assert len(_manifest(twice_html)) == len(_manifest(once_html))
    assert _manifest(twice_html)["font-a"] == _manifest(src)["font-a"]


def test_remove_resource_drops_entry():
    html = _bundle({"keep": _entry("text/javascript", "Zm9v"),
                    "drop": _entry("text/csv", "Q1NW")})
    before = _manifest(html)

    new_html = br.remove_resource(html, "drop")
    after = _manifest(new_html)

    assert "drop" not in after
    assert len(after) == len(before) - 1
    assert "keep" in after
