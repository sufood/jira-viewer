import base64
import json

import build_bundle as B
import decompose_bundle as D


def _fake_bundle(tmpl='"tmpl"'):
    """A minimal bundle: manifest with two resources + a template block. No
    __PRISTINE_HTML resource, so apply() only rewrites the template block."""
    m = {
        "11111111-1111-1111-1111-111111111111":
            {"mime": "font/woff2", "compressed": False,
             "data": base64.b64encode(b"FONT-BYTES-\x00\x01\x02").decode()},
        "22222222-2222-2222-2222-222222222222":
            {"mime": "text/javascript", "compressed": False,
             "data": base64.b64encode(b"var x = 1;").decode()},
    }
    return ('<html><head></head><body>'
            '<script type="__bundler/manifest">' + json.dumps(m) + '</script>'
            '<script type="__bundler/template">' + tmpl + '</script>'
            '</body></html>')


def test_decompose_blanks_source_and_extracts_blobs():
    html = _fake_bundle()
    skeleton, blobs = D.decompose(html)
    assert "@@TEMPLATE@@" in skeleton               # app source removed
    assert len(blobs) == 2
    # resource data no longer inline in the skeleton
    for v_data in ("FONT-BYTES",):
        assert base64.b64encode(b"FONT-BYTES-\x00\x01\x02").decode() not in skeleton
    assert '"@@11111111-1111-1111-1111-111111111111@@"' in skeleton


def test_assemble_reverses_decompose_byte_identical(tmp_path):
    html = _fake_bundle()
    skeleton, blobs = D.decompose(html)
    vd = tmp_path / "vendor"
    vd.mkdir()
    for uuid, raw in blobs.items():
        (vd / uuid).write_bytes(raw)
    # Rebuild with the bundle's own source ("tmpl") -> byte-identical original.
    recon = B.assemble(skeleton, str(vd), "tmpl")
    assert recon == html


def test_assemble_injects_new_source(tmp_path):
    html = _fake_bundle()
    skeleton, blobs = D.decompose(html)
    vd = tmp_path / "vendor"
    vd.mkdir()
    for uuid, raw in blobs.items():
        (vd / uuid).write_bytes(raw)
    recon = B.assemble(skeleton, str(vd), "BRAND-NEW-SOURCE")
    assert '"BRAND-NEW-SOURCE"' in recon            # new template baked in
    assert "@@TEMPLATE@@" not in recon
    # vendored blobs still restored intact
    assert base64.b64encode(b"var x = 1;").decode() in recon
