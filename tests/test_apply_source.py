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
    subprocess.run([sys.executable, "apply_source.py", "--extract",
                    "--bundle", str(work), "--src", str(src)], check=True)
    subprocess.run([sys.executable, "apply_source.py",
                    "--bundle", str(work), "--src", str(src)], check=True)
    html = work.read_text(encoding="utf-8")
    tmpl = json.loads(_block(html, "template"))
    assert "<x-dc>" in tmpl

def test_edit_lands_in_template_and_pristine(tmp_path):
    work = tmp_path / "b.html"; shutil.copy(BUNDLE, work)
    src = tmp_path / "s.html"
    subprocess.run([sys.executable, "apply_source.py", "--extract",
                    "--bundle", str(work), "--src", str(src)], check=True)
    text = src.read_text(encoding="utf-8")
    marker = "/*__WSJF_MERGE_MARKER__*/"
    src.write_text(text.replace("</x-dc>", marker + "</x-dc>", 1), encoding="utf-8")
    subprocess.run([sys.executable, "apply_source.py",
                    "--bundle", str(work), "--src", str(src)], check=True)
    html = work.read_text(encoding="utf-8")
    assert marker in json.loads(_block(html, "template"))
    assert marker in _pristine(html)   # serializer copy updated too
