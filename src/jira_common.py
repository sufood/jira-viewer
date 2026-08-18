#!/usr/bin/env python3
"""Shared helpers for the Jira ⇄ CSV toolkit: env, CSV I/O, ADF, Jira client."""

import csv
import json
import os
import re
import sys
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
    "#", "Division", "Initiative", "Opportunity", "AI-fit", "Status",
    "Key people", "Systems", "Themes", "Summary", "Description",
    "Jira Key", "Jira URL", "Stage", "Swimlane",
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


CONTEXT_KEYS = ["Division", "Initiative", "AI-fit", "Status", "Key people", "Systems", "Themes", "Summary"]


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
    # Initiative and Status are optional per-story facets; only emit a label
    # when a value is present (an empty value would produce a bare "init-").
    if row.get("Initiative", "").strip():
        labels.append(slug(row["Initiative"], "init-"))
    if row.get("Status", "").strip():
        labels.append(slug(row["Status"], "status-"))
    return sorted(set(labels))


# --- Fallbacks for issues WITHOUT a context block --------------------------
# When an issue authored directly in Jira has no machine-readable context block,
# `apply_fallbacks` fills the still-BLANK metadata columns from a fixed ladder,
# never overwriting a value the context block or a human already set.
#
# Closed vocabularies let us recover AI-fit / Status EXACTLY from the slug labels
# `push` emits (`ai-fit-medium-high`, `status-endorsed`, ...). Free-text fields
# are never de-slugged (lossy); they fall back to real Jira fields instead.
CLOSED_VOCAB = {
    "AI-fit": {"high": "High", "medium-high": "Medium-High",
               "medium": "Medium", "medium-low": "Medium-Low"},
    "Status": {"funded": "Funded", "endorsed": "Endorsed",
               "prioritised": "Prioritised", "parked": "Parked"},
}

# Slug-label prefixes this toolkit writes; excluded when harvesting an issue's
# own free-text labels as Themes so we don't echo our own facets back.
TOOLKIT_LABEL_PREFIXES = ("div-", "ai-fit-", "theme-", "init-", "status-")

# Built-in defaults for the fill-blank ladder; a settings.yaml `defaults:` block
# is shallow-merged over this (and its `infer` sub-map deep-merged).
DEFAULTS_FALLBACK = {
    "division": "N/A",     # required — blank-Division rows drop off the map
    "ai_fit": "Medium",    # card legend colour
    "status": "",          # blank sorts alongside Prioritised
    "infer": {             # each Jira-native inference source, individually gated
        "aifit_from_label": True,        # ai-fit-* slug label -> AI-fit
        "status_from_label": True,       # status-* slug label -> Status
        "division_from_component": True,  # component_division map -> Division
        "initiative_from_parent": True,   # epic/parent summary -> Initiative
        "key_people_from_assignee": True,  # assignee display name -> Key people
        "systems_from_components": True,   # components -> Systems
        "themes_from_labels": True,        # non-toolkit labels -> Themes
        "summary_from_tldr": True,         # leading "TLDR;" line -> Summary
    },
    "component_division": {},  # exact {Jira component name: Division} map
}


def _vocab_from_labels(labels, prefix, vocab):
    """Recover a closed-vocab value from the first `prefix`-slug label, or ""."""
    for lab in labels:
        if lab.startswith(prefix):
            hit = vocab.get(lab[len(prefix):].lower())
            if hit:
                return hit
    return ""


def apply_fallbacks(row, issue, defaults=None):
    """Fill BLANK metadata columns of `row` for an issue with no (or a partial)
    context block, using a fixed ladder. NEVER overwrites a non-empty cell, so a
    real context block value or a manual CSV edit always wins. Mutates `row` in
    place and returns {column: source} describing what was filled (for reporting).
    """
    d = {**DEFAULTS_FALLBACK, **(defaults or {})}
    infer = {**DEFAULTS_FALLBACK["infer"], **(d.get("infer") or {})}
    comp_div = d.get("component_division") or {}
    fields = issue.get("fields", {}) or {}
    labels = fields.get("labels") or []
    filled = {}

    def put(col, value, source):
        if value and not (row.get(col, "") or "").strip():
            row[col] = value
            filled[col] = source

    comps = [c.get("name", "") for c in (fields.get("components") or [])
             if c.get("name")]
    assignee = (fields.get("assignee") or {}).get("displayName", "") or ""
    parent = (((fields.get("parent") or {}).get("fields") or {})
              .get("summary", "") or "")

    # AI-fit: ai-fit-* label (exact) -> static default
    if infer.get("aifit_from_label"):
        put("AI-fit", _vocab_from_labels(labels, "ai-fit-",
                                          CLOSED_VOCAB["AI-fit"]), "label")
    put("AI-fit", d.get("ai_fit", ""), "default")

    # Status: status-* label (exact) -> static default
    if infer.get("status_from_label"):
        put("Status", _vocab_from_labels(labels, "status-",
                                         CLOSED_VOCAB["Status"]), "label")
    put("Status", d.get("status", ""), "default")

    # Division (required): component->division map -> static default
    if infer.get("division_from_component"):
        for c in comps:
            if c in comp_div:
                put("Division", comp_div[c], "component")
                break
    put("Division", d.get("division", ""), "default")

    # Initiative: epic/parent summary
    if infer.get("initiative_from_parent"):
        put("Initiative", parent, "parent")

    # Key people: assignee display name
    if infer.get("key_people_from_assignee"):
        put("Key people", assignee, "assignee")

    # Systems: the issue's components
    if infer.get("systems_from_components"):
        put("Systems", "; ".join(comps), "components")

    # Themes: the issue's own (non-toolkit) labels
    if infer.get("themes_from_labels"):
        themes = [l for l in labels
                  if not l.lower().startswith(TOOLKIT_LABEL_PREFIXES)]
        put("Themes", "; ".join(themes), "labels")

    # Summary: a leading "TLDR;" line in the pulled Description body
    if infer.get("summary_from_tldr"):
        m = re.match(r"\s*TLDR;\s*(.+)", row.get("Description", "") or "")
        if m:
            put("Summary", m.group(1).strip(), "tldr")

    return filled


def issue_content(issue, current=None):
    """Extract the CSV content columns from a Jira issue's `fields`.

    Returns {'Opportunity': ...} always, plus 'Description' and any context-block
    metadata (Division / Initiative / AI-fit / ...) ONLY when the API actually
    returned a `description` — never clobbers the body with an empty string just
    because the field was absent from the response. `current` supplies the
    fallback values (e.g. the existing CSV row) when a field is missing. This is
    the shared mapping used by both `pull` (refresh a linked row) and `import`
    (build a fresh row from a searched issue)."""
    current = current or {}
    fields = issue.get("fields", {})
    vals = {"Opportunity": fields.get("summary", current.get("Opportunity", ""))}
    if "description" in fields:
        doc = fields.get("description") or {"type": "doc", "version": 1,
                                            "content": []}
        vals["Description"] = adf_to_markdown(doc)
        ctx = parse_context_block(doc)
        for k in CONTEXT_KEYS:
            if k in ctx:
                vals[k] = ctx[k]
    return vals


def stage_for_status(columns, status_id, status_name):
    """Map a Jira status to its board column (the kanban 'stage'). `columns`
    is the list from Jira.board_config. Falls back to the raw status name when
    the status isn't mapped to any column (or no board config is available)."""
    for col in columns or []:
        if str(status_id) in col.get("statusIds", []):
            return col.get("name", status_name)
    return status_name


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
        `labels`, `assignee`, `components` and `parent` feed the no-context-block
        fill ladder (`apply_fallbacks`). None on failure."""
        resp = self._request(
            "GET", f"/rest/api/3/issue/{key}",
            params={"fields": "summary,description,labels,assignee,components,"
                    "parent,issuetype,project"},
        )
        return resp.json() if resp.status_code == 200 else None

    def find_board(self, project_key: str) -> int | None:
        """Return the first Agile board id for a project, or None."""
        resp = self._request(
            "GET", "/rest/agile/1.0/board",
            params={"projectKeyOrId": project_key, "maxResults": 50})
        if resp.status_code != 200:
            return None
        vals = resp.json().get("values", [])
        return vals[0]["id"] if vals else None

    def board_config(self, board_id) -> list[dict] | None:
        """Return the board's ordered kanban columns as
        [{"name": str, "statusIds": [str, ...]}, ...] via the Agile API's
        board configuration (the canonical column→status mapping). None on
        failure. Note: this endpoint returns columns/statuses but not the
        query-swimlane definitions (a long-standing Jira gap), so swimlane
        membership is reconstructed separately by running each lane's JQL."""
        resp = self._request(
            "GET", f"/rest/agile/1.0/board/{board_id}/configuration")
        if resp.status_code != 200:
            return None
        cols = resp.json().get("columnConfig", {}).get("columns", [])
        return [{"name": c.get("name", ""),
                 "statusIds": [str(s.get("id")) for s in c.get("statuses", [])]}
                for c in cols]

    def search_issues(self, jql: str, fields: list[str],
                      page_size: int = 100) -> list[dict]:
        """Return every issue matching `jql` via the enhanced JQL search
        endpoint (`/rest/api/3/search/jql`), paging with `nextPageToken` until
        exhausted. `fields` is the list of issue fields to fetch (the issue
        `key` always comes back at the top level regardless). The older
        `/rest/api/3/search` GET endpoint is deprecated by Atlassian; this uses
        the token-paginated replacement. Raises RuntimeError on a non-200."""
        issues, token = [], None
        while True:
            body = {"jql": jql, "fields": fields, "maxResults": page_size}
            if token:
                body["nextPageToken"] = token
            resp = self._request(
                "POST", "/rest/api/3/search/jql", json=body,
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"JQL search failed: HTTP {resp.status_code} "
                    f"{resp.text[:300]}")
            data = resp.json()
            batch = data.get("issues", [])
            issues.extend(batch)
            token = data.get("nextPageToken")
            if not token or not batch:
                break
        return issues


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


def connect():
    """Build a Jira client from env and confirm authentication. Returns the
    connected client, or raises SystemExit with an actionable message. Used on
    its own by read-only flows (e.g. a raw-JQL `import`) and as the first step
    of `connect_and_preflight`."""
    try:
        jira = Jira(os.environ["JIRA_BASE_URL"], os.environ["JIRA_EMAIL"],
                    os.environ["JIRA_API_TOKEN"])
    except KeyError as e:
        sys.exit(f"Missing environment variable: {e}")

    me = jira.whoami()
    if me is None:
        sys.exit("ERROR: authentication failed (check JIRA_EMAIL / "
                 "JIRA_API_TOKEN; scoped tokens need read+write:jira-work, "
                 "or read:jira-work for read-only pull/import).")
    print(f"Authenticated as: {me.get('displayName')}")
    return jira


def connect_and_preflight(project_key, issue_type, require_create=False):
    """Build a Jira client from env and run preflight checks: auth → project
    visible → issue type available, and (when require_create, i.e. for push)
    → Create Issues permission. Pass issue_type=None to skip the issue-type
    check (read-only flows don't create issues). Returns the connected Jira
    client. Raises SystemExit with an actionable message on any failure."""
    jira = connect()

    project = jira.check_project(project_key)
    if project is None:
        visible = ", ".join(p["key"] for p in jira.list_projects()) or "(none)"
        sys.exit(f"ERROR: project {project_key!r} not visible. "
                 f"Projects you can see: {visible}")
    type_names = [t["name"] for t in project.get("issueTypes", [])]
    if issue_type and type_names and issue_type not in type_names:
        sys.exit(f"ERROR: project has no {issue_type!r} issue type. "
                 f"Available: {', '.join(type_names)}")
    suffix = f" (issue type {issue_type})" if issue_type else ""
    print(f"Target project: {project['key']} — {project['name']}{suffix}")

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
