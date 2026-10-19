import jira_common as jc

CONTEXT_KEYS = ["Division", "AI-fit", "Key people", "Systems", "Themes", "Summary"]


def test_context_block_roundtrips_exact_values(sample_row):
    nodes = jc.build_context_block(sample_row)      # [rule, bulletList]
    doc = {"type": "doc", "version": 1, "content": [jc.adf_paragraph("body")] + nodes}
    parsed = jc.parse_context_block(doc)
    for k in CONTEXT_KEYS:
        assert parsed[k] == sample_row[k]           # exact, un-slugified


def test_build_description_body_then_context(sample_row):
    doc = jc.build_description(sample_row)
    assert doc["content"][0]["type"] == "heading"   # body first
    assert doc["content"][-2]["type"] == "rule"     # then rule + context
    assert doc["content"][-1]["type"] == "bulletList"


def test_slug_and_labels(sample_row):
    assert jc.slug("Portfolio & FAO", "div-") == "div-portfolio-fao"
    labels = jc.build_labels(sample_row)
    assert "div-portfolio-fao" in labels
    assert "ai-fit-high" in labels
    assert any(l.startswith("theme-") for l in labels)


def test_parse_context_block_missing_returns_empty():
    doc = {"type": "doc", "version": 1, "content": [jc.adf_paragraph("no context")]}
    assert jc.parse_context_block(doc) == {}
