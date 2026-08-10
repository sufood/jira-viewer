# tests/test_apply_source.py
import subprocess, shutil, re, json, os, sys
from tests.test_bundle_integrity import _manifest, _block, _resource_text

BUNDLE = "Insignia AI Strategy Map - Jira linked.html"

def _pristine(html):
    man = _manifest(html)
    for uuid, v in man.items():
        if "javascript" in (v.get("mime") or ""):
            t = _resource_text(html, uuid)
            m = re.search(r'window\.__PRISTINE_HTML\s*=\s*("(?:[^"\\]|\\.)*")', t)
            if m:
                return json.loads(m.group(1))
    return None

def test_roundtrip_unchanged(tmp_path):
    work = tmp_path / "b.html"
    shutil.copy(BUNDLE, work)
    src = tmp_path / "s.html"
    subprocess.run([sys.executable, "src/apply_source.py", "--extract",
                    "--bundle", str(work), "--src", str(src)], check=True)
    subprocess.run([sys.executable, "src/apply_source.py",
                    "--bundle", str(work), "--src", str(src)], check=True)
    html = work.read_text(encoding="utf-8")
    tmpl = json.loads(_block(html, "template"))
    assert "<x-dc>" in tmpl

def test_edit_lands_in_template_and_pristine(tmp_path):
    work = tmp_path / "b.html"; shutil.copy(BUNDLE, work)
    src = tmp_path / "s.html"
    subprocess.run([sys.executable, "src/apply_source.py", "--extract",
                    "--bundle", str(work), "--src", str(src)], check=True)
    text = src.read_text(encoding="utf-8")
    marker = "/*__WSJF_MERGE_MARKER__*/"
    src.write_text(text.replace("</x-dc>", marker + "</x-dc>", 1), encoding="utf-8")
    subprocess.run([sys.executable, "src/apply_source.py",
                    "--bundle", str(work), "--src", str(src)], check=True)
    html = work.read_text(encoding="utf-8")
    assert marker in json.loads(_block(html, "template"))
    assert marker in _pristine(html)   # serializer copy updated too


def test_unchanged_apply_is_byte_identical_forms():
    """extract -> apply with no edits reproduces the template block AND the
    __PRISTINE_HTML authoring copy byte-for-byte (the two forms are stable)."""
    import apply_source as A
    html = open(BUNDLE, encoding="utf-8").read()
    out = A.apply(html, A.extract(html))
    assert json.loads(_block(out, "template")) == json.loads(_block(html, "template"))
    assert _pristine(out) == _pristine(html)


def test_apply_preserves_pristine_standalone_structure():
    """The template block is runtime-form (uuid script refs, sc-camel-on-*);
    __PRISTINE_HTML is the standalone authoring form (./support.js, onClick).
    apply() must keep pristine in authoring form and propagate edits, not
    clobber it with the runtime-form source."""
    import apply_source as A
    html = open(BUNDLE, encoding="utf-8").read()
    marker = "/*__PIN_STANDALONE__*/"
    edited = A.extract(html).replace("</x-dc>", marker + "</x-dc>", 1)
    out = A.apply(html, edited)

    pris = _pristine(out)
    assert pris is not None
    head = pris[: pris.find("</helmet>")]
    markup = pris[pris.find("</helmet>"): pris.find("</x-dc>")]

    # standalone serializer structure intact
    assert "./support.js" in pris and "./page-source.js" in pris
    assert not re.search(r'src="[0-9a-f]{8}-[0-9a-f-]+"', head), "uuid script refs leaked into pristine head"
    # authoring-form markup (not the runtime de-sugared form), edit propagated
    assert marker in markup
    assert "onClick=" in markup and "sc-camel-on" not in markup
    # <select> is de-sugared, but the table-family raw tags stay wrapped so the
    # standalone's live <x-dc> survives HTML table foster-parenting (real <table>
    # tags would drop the <sc-for> row loops on parse).
    assert "<select" in markup and "sc-raw-select" not in markup
    assert "<sc-raw-table" in markup and "sc-raw-tbody" in markup

    # meanwhile the template block is the runtime form
    tmpl = json.loads(_block(out, "template"))
    tmk = tmpl[tmpl.find("</helmet>"): tmpl.find("</x-dc>")]
    assert "sc-camel-on" in tmk and "onClick=" not in tmk


def test_apply_puts_plex_mono_in_pristine_font_link():
    """The Priority views use IBM Plex Mono. The runtime form declares it via
    inline @font-face, but the shipped output is built from the pristine
    (authoring) copy, which loads fonts from a Google Fonts <link>. apply() must
    top that link up with IBM Plex Mono, or shipped mono numerics fall back."""
    import apply_source as A
    html = open(BUNDLE, encoding="utf-8").read()
    out = A.apply(html, A.extract(html))
    pris = _pristine(out)
    head = pris[: pris.find("</helmet>")]
    m = re.search(r'<link href="https://fonts\.googleapis\.com/css2\?[^"]*"', head)
    assert m, "pristine has no Google Fonts link"
    assert "IBM+Plex+Mono" in m.group(0), "IBM Plex Mono missing from the shipped font link"
    # idempotent — a second apply must not add it twice
    out2 = A.apply(out, A.extract(out))
    assert _pristine(out2)[: _pristine(out2).find("</helmet>")].count("IBM+Plex+Mono") == 1


def test_apply_raises_on_malformed_source():
    """apply() must refuse to write a broken pristine rather than silently
    clobber it when the source lacks </helmet> or </x-dc>."""
    import apply_source as A
    import pytest
    html = open(BUNDLE, encoding="utf-8").read()
    bad = A.extract(html).replace("</x-dc>", "<!--gone-->", 1)
    with pytest.raises(ValueError):
        A.apply(html, bad)
