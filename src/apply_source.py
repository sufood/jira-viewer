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

# --- Runtime <-> authoring form -------------------------------------------
# The `__bundler/template` block is the *runtime* form (what the loader injects
# directly). `window.__PRISTINE_HTML` is the *authoring* form that the app's own
# serializer (downloadPage) feeds to support.js to rebuild a shareable page.
# The two differ ONLY inside the markup region (</helmet>..</x-dc>) by three
# bijective rewrites (verified byte-exact against the shipped bundle):
#   sc-camel-on-<kebab>=  <-> on<Pascal>=      (event handlers)
#   <sc-raw-<tag>         <-> <<tag>           (raw form controls, e.g. select)
#   data-mut=""           <-> data-mut         (bare mutability marker)
# The <helmet> head (fonts / ./support.js refs) and the dc-body are otherwise
# form-independent, so we keep pristine's own head and splice the transformed
# markup + the (identical-form) dc-body from the edited source.
_PRISTINE_RE = re.compile(r'window\.__PRISTINE_HTML\s*=\s*"(?:[^"\\]|\\.)*"')

def _kebab_to_pascal(k):
    return "".join(w.capitalize() for w in k.split("-"))

def runtime_to_authoring(markup):
    markup = re.sub(r'sc-camel-on-([a-z-]+)=',
                    lambda m: "on" + _kebab_to_pascal(m.group(1)) + "=", markup)
    markup = re.sub(r'(</?)sc-raw-([a-z0-9]+)', r'\1\2', markup)
    markup = markup.replace('data-mut=""', 'data-mut')
    return markup

def _ensure_priority_fonts(head):
    """The Priority (WSJF) views use IBM Plex Mono. In the runtime template that
    is an inline @font-face, but the authoring/pristine form loads fonts from a
    Google Fonts <link> — so the regenerated/locked output (built from pristine)
    must request IBM Plex Mono there too, or its mono numerics fall back to a
    system font. `apply_source` doesn't sync the head (the two forms' heads
    diverge: uuid script refs vs ./support.js), so we top up just this one link.
    Idempotent."""
    if "IBM+Plex+Mono" in head or "IBM Plex Mono" in head:
        return head
    m = re.search(r'<link href="https://fonts\.googleapis\.com/css2\?[^"]*"', head)
    if not m:
        return head
    link = m.group(0)
    add = "&family=IBM+Plex+Mono:wght@400;500;600"
    new_link = link.replace("&display=swap", add + "&display=swap", 1) \
        if "&display=swap" in link else link[:-1] + add + '"'
    return head[:m.start()] + new_link + head[m.end():]

def _sync_pristine(old_pristine, new_source):
    """Return the authoring-form pristine updated with new_source's edits,
    preserving old_pristine's own <helmet>/head (its ./support.js structure).

    NOTE: the head is otherwise taken verbatim from the old pristine — edits to
    the source <head> (meta, <link>, <style>) do NOT propagate here, because the
    two forms' heads diverge (uuid script refs vs ./support.js) and re-deriving
    one from the other is out of scope. The only head top-up we make is the
    Priority-views font link (see _ensure_priority_fonts)."""
    HELMET = "</helmet>"
    a = old_pristine.find(HELMET)
    nb0 = new_source.find(HELMET)
    nx = new_source.find("</x-dc>")
    if a == -1 or nb0 == -1 or nx == -1:
        # Refuse to write a broken/wrong-form pristine rather than silently
        # clobber it with the runtime-form source.
        raise ValueError(
            "apply_source: source is missing </helmet> or </x-dc>; refusing to "
            "write the authoring __PRISTINE_HTML copy")
    head = _ensure_priority_fonts(old_pristine[: a + len(HELMET)])
    markup = runtime_to_authoring(new_source[nb0 + len(HELMET): nx])
    # </x-dc> + dc-body: form-independent except the dc-script open tag, whose
    # bare boolean `data-dc-script` is normalised to `data-dc-script=""` in the
    # runtime form. Restore the bare form on the tag only (count=1).
    core = new_source.rfind("</script>")
    if core == -1:
        raise ValueError("apply_source: source has no dc-body </script>; aborting")
    core_end = core + len("</script>")
    tail = new_source[nx:core_end].replace('data-dc-script=""', 'data-dc-script', 1)
    # Keep pristine's own trailing (its </body></html> whitespace differs from
    # the runtime form's and is form-specific).
    trailing = old_pristine[old_pristine.rfind("</script>") + len("</script>"):]
    return head + markup + tail + trailing

def apply(html, source):
    # 1. Replace the template block with the runtime-form source. The bundler
    # escapes "</" as a JSON unicode escape so an embedded "</script>" inside the
    # source can't close the outer <script type="__bundler/template"> wrapper.
    new_tmpl_json = json.dumps(source).replace("</", "<\\u002F")
    m = TMPL_RE.search(html)
    html = html[:m.start(2)] + new_tmpl_json + html[m.end(2):]
    # 2. Sync the __PRISTINE_HTML authoring copy in place (see notes above).
    mman, manifest = _manifest(html)
    uuid = _find_pristine_uuid(html, manifest)
    if uuid:
        v = manifest[uuid]; text = _dec(v)
        pm = _PRISTINE_RE.search(text)
        old_pristine = json.loads(pm.group(0).split("=", 1)[1].strip())
        new_pristine = _sync_pristine(old_pristine, source)
        esc = json.dumps(new_pristine).replace("</", "<\\/")
        replacement = "window.__PRISTINE_HTML = " + esc
        text = _PRISTINE_RE.sub(lambda _m: replacement, text, count=1)
        manifest[uuid] = _enc(v, text)
        new_man = json.dumps(manifest, separators=(",", ":"))
        html = html[:mman.start(2)] + new_man + html[mman.end(2):]
    return html

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", default="Insignia AI Strategy Map - Jira linked.html")
    ap.add_argument("--src", default="src/strategy-map.src.html")
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
