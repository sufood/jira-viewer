# apply_source.py — extract/apply the editable template source into the bundle.
# Apply mode updates BOTH the live __bundler/template block and the
# __PRISTINE_HTML page-source resource so the app's own serializer stays correct.
import argparse, base64, gzip, io, json, re

MANI_RE = re.compile(r'(<script type="__bundler/manifest">)(.*?)(</script>)', re.S)
TMPL_RE = re.compile(r'(<script type="__bundler/template">)(.*?)(</script>)', re.S)

def _manifest(html):
    m = MANI_RE.search(html); return m, json.loads(m.group(2).strip())

def _dec(v):
    raw = base64.b64decode(v["data"])
    return gzip.decompress(raw).decode("utf-8") if v.get("compressed") else raw.decode("utf-8")

def _enc(v, text):
    data = text.encode("utf-8")
    if v.get("compressed"):
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as g:
            g.write(data)
        data = buf.getvalue()
    v = dict(v); v["data"] = base64.b64encode(data).decode(); return v

def extract(html):
    return json.loads(TMPL_RE.search(html).group(2).strip())

def _find_pristine_uuid(html, manifest):
    for uuid, v in manifest.items():
        if "javascript" in (v.get("mime") or "") and "__PRISTINE_HTML" in _dec(v):
            return uuid
    return None

def apply(html, source):
    # 1. Replace the template block (JSON string of the source HTML).
    # The bundler escapes "</" as a JSON unicode escape (backslash + u002F)
    # in this block so an embedded "</script>" inside the source HTML can't
    # prematurely close the outer <script type="__bundler/template"> wrapper.
    new_tmpl_json = json.dumps(source).replace("</", "<\\u002F")
    m = TMPL_RE.search(html)
    html = html[:m.start(2)] + new_tmpl_json + html[m.end(2):]
    # 2. Rebuild the __PRISTINE_HTML resource to match, preserving its wrapper.
    mman, manifest = _manifest(html)
    uuid = _find_pristine_uuid(html, manifest)
    if uuid:
        v = manifest[uuid]; text = _dec(v)
        esc = json.dumps(source).replace("</", "<\\/")
        replacement = "window.__PRISTINE_HTML = " + esc
        text = re.sub(r'window\.__PRISTINE_HTML\s*=\s*"(?:[^"\\]|\\.)*"',
                      lambda _m: replacement, text, count=1)
        manifest[uuid] = _enc(v, text)
        new_man = json.dumps(manifest, separators=(",", ":"))
        html = html[:mman.start(2)] + new_man + html[mman.end(2):]
    return html

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", default="Insignia AI Strategy Map - Jira linked.html")
    ap.add_argument("--src", default="app/strategy-map.src.html")
    ap.add_argument("--extract", action="store_true")
    a = ap.parse_args()
    html = open(a.bundle, encoding="utf-8").read()
    if a.extract:
        open(a.src, "w", encoding="utf-8").write(extract(html))
        print("extracted ->", a.src); return
    source = open(a.src, encoding="utf-8").read()
    open(a.bundle, "w", encoding="utf-8").write(apply(html, source))
    print("applied", a.src, "->", a.bundle)

if __name__ == "__main__":
    main()
