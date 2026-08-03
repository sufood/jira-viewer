#!/usr/bin/env python3
"""Decode / edit / re-encode the single-file app bundle.

The bundle stores resources in a JSON manifest inside
<script type="__bundler/manifest">…</script>, each value
{mime, compressed, data} where data is base64 of gzip when compressed.
"""

import base64
import gzip
import io
import json
import re

_MANIFEST_RE = re.compile(
    r'(<script type="__bundler/manifest">)(.*?)(</script>)', re.S)


def _manifest(html):
    m = _MANIFEST_RE.search(html)
    if not m:
        raise ValueError("no __bundler/manifest block found")
    return m, json.loads(m.group(2))


def get_resource_text(html, uuid):
    _, manifest = _manifest(html)
    v = manifest[uuid]
    raw = base64.b64decode(v["data"])
    if v.get("compressed"):
        raw = gzip.decompress(raw)
    return raw.decode("utf-8")


def find_resource_with(html, needle):
    """UUID of the first text/javascript resource containing `needle`."""
    _, manifest = _manifest(html)
    for uuid, v in manifest.items():
        if "javascript" not in (v.get("mime") or ""):
            continue
        raw = base64.b64decode(v["data"])
        if v.get("compressed"):
            raw = gzip.decompress(raw)
        if needle in raw.decode("utf-8", "replace"):
            return uuid
    return None


def edit_resource(html, uuid, transform):
    """Return new HTML with resource `uuid`'s text replaced by transform(text).
    Recompresses deterministically (gzip mtime=0) and rebuilds the manifest."""
    m, manifest = _manifest(html)
    v = dict(manifest[uuid])
    raw = base64.b64decode(v["data"])
    text = gzip.decompress(raw).decode("utf-8") if v.get("compressed") \
        else raw.decode("utf-8")
    new_text = transform(text)
    data = new_text.encode("utf-8")
    if v.get("compressed"):
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as g:
            g.write(data)
        data = buf.getvalue()
    v["data"] = base64.b64encode(data).decode()
    manifest[uuid] = v
    new_manifest = json.dumps(manifest, separators=(",", ":"))
    return html[:m.start(2)] + new_manifest + html[m.end(2):]
