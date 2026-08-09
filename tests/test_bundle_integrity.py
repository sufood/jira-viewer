# tests/test_bundle_integrity.py
import json, re, base64, gzip, os
import pytest

BUNDLE = "Insignia AI Strategy Map - Jira linked.html"

def _block(html, kind):
    m = re.search(r'<script type="__bundler/%s">(.*?)</script>' % kind, html, re.S)
    assert m, f"missing __bundler/{kind} block"
    return m.group(1).strip()

def _manifest(html):
    return json.loads(_block(html, "manifest"))

def _resource_text(html, uuid):
    v = _manifest(html)[uuid]
    raw = base64.b64decode(v["data"])
    if v.get("compressed"):
        raw = gzip.decompress(raw)
    return raw.decode("utf-8")

def load():
    with open(BUNDLE, encoding="utf-8") as f:
        return f.read()

def test_manifest_and_template_parse():
    html = load()
    man = _manifest(html)
    tmpl = json.loads(_block(html, "template"))
    assert isinstance(man, dict) and man
    assert "<x-dc>" in tmpl

def test_every_template_uuid_resolves():
    html = load()
    man = _manifest(html)
    tmpl = json.loads(_block(html, "template"))
    for uuid in re.findall(r'src="([0-9a-f-]{36})"', tmpl):
        assert uuid in man, f"template references missing resource {uuid}"

def test_dc_runtime_present():
    html = load()
    man = _manifest(html)
    texts = []
    for uuid, v in man.items():
        if "javascript" in (v.get("mime") or ""):
            texts.append(_resource_text(html, uuid))
    assert any("GENERATED from dc-runtime" in t for t in texts)

def test_pristine_html_matches_template():
    html = load()
    tmpl = json.loads(_block(html, "template"))
    man = _manifest(html)
    pristine = None
    for uuid, v in man.items():
        if "javascript" not in (v.get("mime") or ""):
            continue
        t = _resource_text(html, uuid)
        m = re.search(r'window\.__PRISTINE_HTML\s*=\s*("(?:[^"\\]|\\.)*")', t)
        if m:
            pristine = json.loads(m.group(1))
            break
    assert pristine is not None, "no __PRISTINE_HTML resource found"
    assert "<x-dc>" in pristine
    def dc_body(s):
        # data-dc-script appears as a bare boolean attribute in the serialized
        # __PRISTINE_HTML copy but as data-dc-script="" in the live template
        # block; accept either form.
        mm = re.search(r'data-dc-script(?:="")?[^>]*>(.*?)</script>', s, re.S)
        return mm.group(1) if mm else None
    assert dc_body(pristine) == dc_body(tmpl), "__PRISTINE_HTML component drifted from template"
