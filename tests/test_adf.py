import jira_common as jc


def test_markdown_to_adf_heading_bullets_bold():
    doc = jc.markdown_to_adf("## Problem\n\n**Core:** x\n\n- a\n- b")
    assert doc["type"] == "doc" and doc["version"] == 1
    types = [n["type"] for n in doc["content"]]
    assert types == ["heading", "paragraph", "bulletList"]
    assert doc["content"][0]["attrs"]["level"] == 3
    marks = doc["content"][1]["content"][0].get("marks")
    assert marks == [{"type": "strong"}]


def test_adf_to_markdown_inverts_body():
    md = "## Problem\n\n**Core:** x\n\n- a\n- b"
    doc = jc.markdown_to_adf(md)
    out = jc.adf_to_markdown(doc)
    assert out == md


def test_adf_to_markdown_ignores_context_block():
    doc = jc.markdown_to_adf("Body line")
    doc["content"].append({"type": "rule"})
    doc["content"].append({
        "type": "bulletList",
        "content": [{"type": "listItem",
                     "content": [jc.adf_paragraph("Division: X")]}],
    })
    assert jc.adf_to_markdown(doc) == "Body line"


def test_adf_to_markdown_unknown_node_degrades_to_text():
    doc = {"type": "doc", "version": 1, "content": [
        {"type": "panel", "content": [jc.adf_paragraph("kept")]}]}
    assert "kept" in jc.adf_to_markdown(doc)
