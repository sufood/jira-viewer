import pathlib
import bundle_common as bc

SRC = pathlib.Path(__file__).resolve().parent.parent / \
    "Insignia AI Strategy Map - Jira linked.html"
PRISTINE_UUID = "3a33ba6c-5488-4bcb-a34b-1e60440a9449"


def test_find_pristine_resource():
    html = SRC.read_text(encoding="utf-8")
    uuid = bc.find_resource_with(html, "__PRISTINE_HTML")
    assert uuid == PRISTINE_UUID


def test_roundtrip_identity_rebuilds_valid_bundle(tmp_path):
    html = SRC.read_text(encoding="utf-8")
    out = bc.edit_resource(html, PRISTINE_UUID, lambda s: s)   # identity
    assert bc.get_resource_text(out, PRISTINE_UUID) == \
           bc.get_resource_text(html, PRISTINE_UUID)
    assert '__bundler/manifest' in out and len(out) > 900_000


def test_edit_resource_injects_text():
    html = SRC.read_text(encoding="utf-8")
    out = bc.edit_resource(html, PRISTINE_UUID,
                           lambda s: s.replace("<\\/head>",
                                               "<x-marker><\\/x-marker><\\/head>", 1))
    assert "<x-marker>" in bc.get_resource_text(out, PRISTINE_UUID)
