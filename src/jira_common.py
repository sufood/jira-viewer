#!/usr/bin/env python3
"""Shared helpers for the Jira ⇄ CSV toolkit: env, CSV I/O, ADF, Jira client."""

import csv
import json
import os
import re
import time

import requests

# Use the OS trust store (macOS Keychain / Windows cert store) when available.
# This makes corporate TLS-inspection proxies (Zscaler, Netskope, ...) work
# without extra configuration:  pip install truststore
try:
    import truststore
    truststore.inject_into_ssl()
    _TRUSTSTORE = True
except ImportError:
    _TRUSTSTORE = False

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


class Jira:
    def __init__(self, base_url: str, email: str, token: str):
        self.base = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.auth = (email, token)
        self.session.headers.update({"Accept": "application/json"})

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = f"{self.base}{path}"
        for attempt in range(5):
            resp = self.session.request(method, url, timeout=30, **kwargs)
            if resp.status_code == 429:  # rate limited
                wait = int(resp.headers.get("Retry-After", 2 ** attempt))
                print(f"  rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            return resp
        resp.raise_for_status()
        return resp

    def find_account_id(self, name: str) -> str | None:
        """Return accountId only when exactly one active user matches."""
        resp = self._request(
            "GET", "/rest/api/3/user/search", params={"query": name}
        )
        if resp.status_code != 200:
            return None
        matches = [u for u in resp.json() if u.get("active")]
        return matches[0]["accountId"] if len(matches) == 1 else None

    def whoami(self) -> dict | None:
        """Confirm credentials work; returns account info or None."""
        resp = self._request("GET", "/rest/api/3/myself")
        return resp.json() if resp.status_code == 200 else None

    def can_create_issues(self, project_key: str) -> bool | None:
        """True/False if the USER has Create Issues permission in the
        project; None if the check itself failed. Note: this reflects user
        permissions, not API-token scopes — a read-scoped token can still
        report True here and then fail on create."""
        resp = self._request(
            "GET", "/rest/api/3/mypermissions",
            params={"projectKey": project_key,
                    "permissions": "CREATE_ISSUES"},
        )
        if resp.status_code != 200:
            return None
        perm = resp.json().get("permissions", {}).get("CREATE_ISSUES", {})
        return perm.get("havePermission")

    def check_project(self, project_key: str) -> dict | None:
        """Return project info (incl. issue types) if visible, else None."""
        resp = self._request(
            "GET", f"/rest/api/3/project/{project_key}",
            params={"expand": "issueTypes"},
        )
        return resp.json() if resp.status_code == 200 else None

    def list_projects(self) -> list[dict]:
        """Projects visible to this account (first 50)."""
        resp = self._request(
            "GET", "/rest/api/3/project/search",
            params={"maxResults": 50, "orderBy": "key"},
        )
        if resp.status_code != 200:
            return []
        return resp.json().get("values", [])

    def create_issue(self, payload: dict) -> requests.Response:
        return self._request(
            "POST", "/rest/api/3/issue", json=payload,
            headers={"Content-Type": "application/json"},
        )

    def get_issue(self, key: str) -> dict | None:
        """Fetch an issue. `description` is requested so `pull` can read the
        body + context block back; without it the API omits the field entirely.
        None on failure."""
        resp = self._request(
            "GET", f"/rest/api/3/issue/{key}",
            params={"fields":
                    "summary,description,labels,assignee,issuetype,project"},
        )
        return resp.json() if resp.status_code == 200 else None


def append_log(csv_path: str, record: dict) -> None:
    """Append one result row to <csv>.upload-log.csv (created on first use)."""
    log_path = csv_path + ".upload-log.csv"
    fieldnames = ["timestamp", "source_id", "result", "issue_id",
                  "issue_key", "url", "verified", "error"]
    new_file = not os.path.exists(log_path)
    with open(log_path, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if new_file:
            w.writeheader()
        w.writerow(record)


def connect_and_preflight(project_key, issue_type, require_create=False):
    """Build a Jira client from env and run preflight checks: auth → project
    visible → issue type available, and (when require_create, i.e. for push)
    → Create Issues permission. Returns the connected Jira client. Raises
    SystemExit with an actionable message on any failure."""
    import sys
    try:
        jira = Jira(os.environ["JIRA_BASE_URL"], os.environ["JIRA_EMAIL"],
                    os.environ["JIRA_API_TOKEN"])
    except KeyError as e:
        sys.exit(f"Missing environment variable: {e}")

    me = jira.whoami()
    if me is None:
        sys.exit("ERROR: authentication failed (check JIRA_EMAIL / "
                 "JIRA_API_TOKEN; scoped tokens need read+write:jira-work).")
    print(f"Authenticated as: {me.get('displayName')}")

    project = jira.check_project(project_key)
    if project is None:
        visible = ", ".join(p["key"] for p in jira.list_projects()) or "(none)"
        sys.exit(f"ERROR: project {project_key!r} not visible. "
                 f"Projects you can see: {visible}")
    type_names = [t["name"] for t in project.get("issueTypes", [])]
    if type_names and issue_type not in type_names:
        sys.exit(f"ERROR: project has no {issue_type!r} issue type. "
                 f"Available: {', '.join(type_names)}")
    print(f"Target project: {project['key']} — {project['name']} "
          f"(issue type {issue_type})")

    if require_create:
        can_create = jira.can_create_issues(project_key)
        if can_create is False:
            sys.exit(f"ERROR: your user lacks 'Create Issues' permission in "
                     f"{project_key}. Ask the project admin to grant it "
                     f"(Project settings → Permissions).")
        if can_create is None:
            print("  warning: could not verify Create Issues permission; "
                  "continuing")
        else:
            print("Create Issues permission: yes")
    return jira
