#!/usr/bin/env python3
"""Shared helpers for the Jira ⇄ CSV toolkit: env, CSV I/O, ADF, Jira client."""

import csv
import os
import re

COLUMNS = [
    "#", "Division", "Opportunity", "AI-fit", "Key people", "Systems",
    "Themes", "Summary", "Description", "Jira Key", "Jira URL",
]


def load_dotenv(path=".env"):
    """Load KEY=value lines from `path` into os.environ WITHOUT overriding
    variables already set in the real environment."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def read_csv(path):
    """Read a CSV as a list of dict rows; strips the UTF-8 BOM."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fieldnames=None):
    """Atomically write rows with BOM + QUOTE_ALL to match the canonical file."""
    fieldnames = fieldnames or COLUMNS
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})
    os.replace(tmp, path)


def _inline(text):
    """Convert **bold** runs into ADF text nodes with strong marks."""
    nodes = []
    for i, part in enumerate(re.split(r"\*\*(.+?)\*\*", text)):
        if not part: continue
        node = {"type": "text", "text": part}
        if i % 2 == 1: node["marks"] = [{"type": "strong"}]
        nodes.append(node)
    return nodes or [{"type": "text", "text": " "}]


def adf_paragraph(text):
    return {"type": "paragraph", "content": _inline(text)}


def markdown_to_adf_blocks(md):
    """Render description markdown (## headings, - bullets, **bold**,
    paragraphs) into ADF blocks."""
    blocks, para, bullets = [], [], []
    def flush_para():
        if para:
            blocks.append(adf_paragraph(" ".join(para))); para.clear()
    def flush_bullets():
        if bullets:
            blocks.append({"type": "bulletList", "content": [
                {"type": "listItem", "content": [adf_paragraph(b)]}
                for b in bullets]}); bullets.clear()
    for ln in md.splitlines():
        s = ln.strip()
        if s.startswith("## "):
            flush_para(); flush_bullets()
            blocks.append({"type": "heading", "attrs": {"level": 3},
                           "content": [{"type": "text", "text": s[3:].strip()}]})
        elif s.startswith(("- ", "* ")):
            flush_para(); bullets.append(s[2:].strip())
        elif not s:
            flush_para(); flush_bullets()
        else:
            flush_bullets(); para.append(s)
    flush_para(); flush_bullets()
    return blocks


def markdown_to_adf(md):
    """Full ADF doc from description markdown."""
    return {"type": "doc", "version": 1,
            "content": markdown_to_adf_blocks(md)}


def _adf_inline_to_md(nodes):
    parts = []
    for n in nodes:
        text = n.get("text", "")
        if any(m.get("type") == "strong" for m in n.get("marks", [])):
            text = f"**{text}**"
        parts.append(text)
    return "".join(parts)


def _adf_block_to_md(node):
    t = node.get("type")
    if t == "heading":
        level = node.get("attrs", {}).get("level", 3)
        return f"{'#' * (level - 1)} {_adf_inline_to_md(node.get('content', []))}"
    if t == "paragraph":
        return _adf_inline_to_md(node.get("content", []))
    if t == "bulletList":
        lines = []
        for item in node.get("content", []):
            for sub in item.get("content", []):
                lines.append(f"- {_adf_inline_to_md(sub.get('content', []))}")
        return "\n".join(lines)
    # Unknown node: recurse into any content, keep the text.
    inner = [_adf_block_to_md(c) for c in node.get("content", [])]
    return "\n".join(x for x in inner if x)


def adf_to_markdown(doc):
    """Inverse of markdown_to_adf. Stops before the trailing context block
    (the last `rule` node and everything after it)."""
    content = doc.get("content", [])
    cut = len(content)
    for i in range(len(content) - 1, -1, -1):
        if content[i].get("type") == "rule":
            cut = i
            break
    blocks = [_adf_block_to_md(n) for n in content[:cut]]
    return "\n\n".join(b for b in blocks if b)


def slug(text, prefix=""):
    """Jira labels cannot contain spaces; make a safe slug."""
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return f"{prefix}{s}"


def split_multi(value):
    """Split '; '-delimited multi-value cells."""
    return [p.strip() for p in value.split(";") if p.strip()]


CONTEXT_KEYS = ["Division", "AI-fit", "Key people", "Systems", "Themes", "Summary"]


def build_context_block(row):
    """Machine-readable, exact-value carrier appended to every description.
    Returns [rule, bulletList]."""
    lines = [f"{k}: {row.get(k, '')}" for k in CONTEXT_KEYS]
    return [
        {"type": "rule"},
        {"type": "bulletList", "content": [
            {"type": "listItem", "content": [adf_paragraph(line)]}
            for line in lines]},
    ]


def parse_context_block(doc):
    """Read exact metadata values back from the trailing context bulletList.
    Returns {} when no context block is present."""
    content = doc.get("content", [])
    rule_idx = None
    for i in range(len(content) - 1, -1, -1):
        if content[i].get("type") == "rule":
            rule_idx = i
            break
    if rule_idx is None:
        return {}
    result = {}
    for node in content[rule_idx + 1:]:
        if node.get("type") != "bulletList":
            continue
        for item in node.get("content", []):
            for para in item.get("content", []):
                text = _adf_inline_to_md(para.get("content", []))
                if ": " in text:
                    key, _, value = text.partition(": ")
                    if key in CONTEXT_KEYS:
                        result[key] = value
    return result


def build_description(row):
    """Description markdown body + context block, as one ADF doc."""
    doc = markdown_to_adf(row["Description"])
    doc["content"].extend(build_context_block(row))
    return doc


def build_labels(row):
    labels = [slug(row["Division"], "div-"), slug(row["AI-fit"], "ai-fit-")]
    labels += [slug(t, "theme-") for t in split_multi(row["Themes"])]
    return sorted(set(labels))
