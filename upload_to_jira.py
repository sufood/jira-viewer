#!/usr/bin/env python3
"""
Upload insignia-division-stories-clean.csv to Jira Cloud as Epic issues.

Usage:
    export JIRA_BASE_URL="https://yourcompany.atlassian.net"
    export JIRA_EMAIL="you@company.com"
    export JIRA_API_TOKEN="..."          # https://id.atlassian.com/manage-profile/security/api-tokens
    export JIRA_PROJECT_KEY="ABC"

    python upload_to_jira.py --dry-run                # preview payloads, no API calls
    python upload_to_jira.py                          # create issues
    python upload_to_jira.py --assign                 # also look up assignees by name
    python upload_to_jira.py --csv path/to/file.csv   # non-default CSV path

Field mapping:
    Summary      -> summary
    Description  -> description (ADF), with Division / AI Fit / Key People /
                    Systems / Source ID appended as a context block
    Division     -> label  div-<slug>
    AI Fit       -> label  ai-fit-<slug>
    Themes       -> labels theme-<slug>
    Systems      -> description context block only (no labels)
    Source ID    -> description context block only (no labels)

    Idempotency: each successful create is recorded in a state file next
    to the CSV (<csv>.upload-state.json) mapping Source ID -> issue key.
    Re-runs skip rows already in the state file. If the state file is
    missing, the script falls back to skipping rows whose Summary exactly
    matches an existing issue in the project. Keep the state file with
    the CSV (commit it or copy it between machines).
    Key People   -> assignee (first person only, --assign flag; requires an
                    unambiguous accountId match, otherwise left unassigned
                    and reported)

Requires: requests  (pip install requests)
"""

import argparse
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

ISSUE_TYPE = "Epic"
DEFAULT_CSV = "insignia-division-stories-enriched.csv"


# ---------------------------------------------------------------- helpers

def slug(text: str, prefix: str = "") -> str:
    """Jira labels cannot contain spaces; make a safe slug."""
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return f"{prefix}{s}"


def split_multi(value: str) -> list[str]:
    """Split '; '-delimited multi-value cells."""
    return [p.strip() for p in value.split(";") if p.strip()]


def _inline(text: str) -> list:
    """Convert **bold** runs into ADF text nodes with strong marks."""
    nodes = []
    for i, part in enumerate(re.split(r"\*\*(.+?)\*\*", text)):
        if not part: continue
        node = {"type": "text", "text": part}
        if i % 2 == 1: node["marks"] = [{"type": "strong"}]
        nodes.append(node)
    return nodes or [{"type": "text", "text": " "}]


def adf_paragraph(text: str) -> dict:
    return {"type": "paragraph", "content": _inline(text)}


def markdown_to_adf_blocks(md: str) -> list:
    """Render the enriched description markdown (## headings, - bullets,
    **bold**, paragraphs) into ADF blocks."""
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


def build_description(row: dict) -> dict:
    """Enriched markdown description + context block, as ADF."""
    content = markdown_to_adf_blocks(row["Description"])
    context = [
        f"Division: {row['Division']}",
        f"AI fit: {row['AI Fit']}",
        f"Key people: {row['Key People']}",
        f"Systems: {row['Systems']}",
        f"Source ID: {row['Source ID']}",
    ]
    content.append({"type": "rule"})
    content.append(
        {
            "type": "bulletList",
            "content": [
                {"type": "listItem", "content": [adf_paragraph(line)]}
                for line in context
            ],
        }
    )
    return {"type": "doc", "version": 1, "content": content}


VALID_PRIORITIES = {"highest", "high", "medium", "low"}

def build_labels(row: dict) -> list[str]:
    labels = [
        slug(row["Division"], "div-"),
        slug(row["AI Fit"], "ai-fit-"),
    ]
    pri = row.get("Priority", "").strip().lower()
    if pri:
        if pri not in VALID_PRIORITIES:
            raise ValueError(f"non-standard priority {pri!r} "
                             f"(row {row.get('Source ID')})")
        labels.append(f"priority-{pri}")
    labels += [slug(t, "theme-") for t in split_multi(row["Themes"])]
    return sorted(set(labels))


def state_path_for(csv_path: str) -> str:
    """State file lives next to the CSV: <csv>.upload-state.json"""
    return csv_path + ".upload-state.json"


def load_state(path: str) -> dict[str, str]:
    """Map of Source ID -> created Jira issue key."""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(path: str, state: dict[str, str]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


# ---------------------------------------------------------------- jira client

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

    def existing_summaries(self, project_key: str) -> set[str]:
        """Summaries of existing issues (fallback duplicate check)."""
        found: set[str] = set()
        jql = f'project = "{project_key}"'
        next_token = None
        while True:
            payload = {"jql": jql, "fields": ["summary"], "maxResults": 100}
            if next_token:
                payload["nextPageToken"] = next_token
            resp = self._request(
                "POST", "/rest/api/3/search/jql", json=payload,
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code != 200:
                print(f"  warning: could not query existing issues "
                      f"({resp.status_code}); summary fallback disabled")
                return found
            data = resp.json()
            for issue in data.get("issues", []):
                summary = issue["fields"].get("summary")
                if summary:
                    found.add(summary.strip())
            next_token = data.get("nextPageToken")
            if not next_token or data.get("isLast", True):
                return found

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
        """Fetch a just-created issue to confirm it exists. None on failure."""
        resp = self._request(
            "GET", f"/rest/api/3/issue/{key}",
            params={"fields": "summary,labels,assignee,issuetype,project"},
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


# ---------------------------------------------------------------- main

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default=DEFAULT_CSV)
    parser.add_argument("--dry-run", action="store_true",
                        help="print payloads without calling the API")
    parser.add_argument("--assign", action="store_true",
                        help="look up first Key Person and set as assignee")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="per-row detail: payload summary, HTTP status, "
                             "timing, full response identifiers")
    parser.add_argument("--verify", action="store_true",
                        help="after each create, GET the issue back from Jira "
                             "to confirm it exists and the summary matches")
    parser.add_argument("--ca-bundle", metavar="PATH",
                        help="path to a corporate CA bundle (.pem) for "
                             "TLS-inspecting proxies; alternative to "
                             "installing 'truststore'")
    args = parser.parse_args()

    if args.ca_bundle:
        os.environ["REQUESTS_CA_BUNDLE"] = args.ca_bundle

    with open(args.csv, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    required = {"Source ID", "Division", "Summary", "AI Fit",
                "Key People", "Systems", "Themes", "Description"}
    # "Priority" column is optional (present in the enriched CSV)
    missing = required - set(rows[0].keys())
    if missing:
        sys.exit(f"CSV is missing columns: {sorted(missing)}")
    print(f"Loaded {len(rows)} rows from {args.csv}")

    project_key = os.environ.get("JIRA_PROJECT_KEY")
    if not project_key and not args.dry_run:
        sys.exit("JIRA_PROJECT_KEY is not set. Export it first, e.g.\n"
                 '  export JIRA_PROJECT_KEY="ABC"')
    project_key = project_key or "PROJ"  # placeholder for dry-run payloads

    state_path = state_path_for(args.csv)
    state = load_state(state_path)
    if state:
        print(f"State file {state_path}: {len(state)} rows already uploaded")

    jira = None
    existing_summaries: set[str] = set()
    if not args.dry_run:
        try:
            jira = Jira(
                os.environ["JIRA_BASE_URL"],
                os.environ["JIRA_EMAIL"],
                os.environ["JIRA_API_TOKEN"],
            )
        except KeyError as e:
            sys.exit(f"Missing environment variable: {e}")

        # Preflight 1: credentials work at all?
        me = jira.whoami()
        if me is None:
            sys.exit("ERROR: authentication failed (check JIRA_EMAIL and "
                     "JIRA_API_TOKEN). If using a scoped token, it needs at "
                     "least read:jira-work and write:jira-work.")
        print(f"Authenticated as: {me.get('displayName')} "
              f"({me.get('emailAddress', 'email hidden')})")

        # Preflight 2: project exists and is visible?
        project = jira.check_project(project_key)
        if project is None:
            print(f"ERROR: project '{project_key}' doesn't exist on "
                  f"{jira.base} or your account can't see it.",
                  file=sys.stderr)
            visible = jira.list_projects()
            if visible:
                print("\nProjects your account CAN see "
                      f"(set JIRA_PROJECT_KEY to one of these):",
                      file=sys.stderr)
                for p in visible:
                    print(f"  {p['key']:<12} {p['name']}", file=sys.stderr)
            else:
                print("Your account can't see any projects at all — "
                      "ask a Jira admin for access.", file=sys.stderr)
            return 2
        print(f"Target project: {project['key']} — {project['name']}")

        # Preflight 3: does the project offer the issue type we need?
        type_names = [t["name"] for t in project.get("issueTypes", [])]
        if type_names and ISSUE_TYPE not in type_names:
            print(f"ERROR: project has no '{ISSUE_TYPE}' issue type. "
                  f"Available: {', '.join(type_names)}. "
                  f"Edit ISSUE_TYPE at the top of the script.",
                  file=sys.stderr)
            return 2
        print(f"Issue type: {ISSUE_TYPE} (available in project)")

        # Preflight 4: does the USER have Create Issues permission?
        can_create = jira.can_create_issues(project_key)
        if can_create is False:
            print(f"ERROR: your user does not have the 'Create Issues' "
                  f"permission in {project_key}. Ask the project admin to "
                  f"grant it (Project settings -> Permissions).",
                  file=sys.stderr)
            return 2
        if can_create is None:
            print("  warning: could not verify Create Issues permission; "
                  "continuing")
        else:
            print(f"Create Issues permission: yes")

        if not state:
            existing_summaries = jira.existing_summaries(project_key)
            if existing_summaries:
                print(f"No state file, but found {len(existing_summaries)} "
                      f"existing issues; rows with matching summaries "
                      f"will be skipped")

    account_cache: dict[str, str | None] = {}
    created, skipped, failed, unassigned = 0, 0, [], []
    created_keys: list[str] = []
    scope_hint_shown = False
    if args.dry_run:
        can_create = None

    for row in rows:
        source_id = row["Source ID"]
        if source_id in state:
            skipped += 1
            continue
        if row["Summary"].strip()[:255] in existing_summaries:
            skipped += 1
            continue

        fields = {
            "project": {"key": project_key},
            "issuetype": {"name": ISSUE_TYPE},
            "summary": row["Summary"][:255],
            "description": build_description(row),
            "labels": build_labels(row),
        }

        if args.assign:
            first_person = split_multi(row["Key People"])[0]
            if first_person not in account_cache:
                account_cache[first_person] = (
                    jira.find_account_id(first_person) if jira else None
                )
            account_id = account_cache[first_person]
            if account_id:
                fields["assignee"] = {"accountId": account_id}
            else:
                unassigned.append((row["Source ID"], first_person))

        payload = {"fields": fields}

        if args.dry_run:
            print(f"\n--- row {source_id}: {row['Summary']}")
            print(json.dumps(payload, indent=2, ensure_ascii=False)[:800])
            created += 1
            continue

        if args.verbose:
            assignee = fields.get("assignee", {}).get("accountId", "none")
            print(f"\n[row {source_id}] POST /rest/api/3/issue")
            print(f"  summary : {fields['summary'][:80]}")
            print(f"  labels  : {', '.join(fields['labels'])}")
            print(f"  assignee: {assignee}")

        started = time.monotonic()
        resp = jira.create_issue(payload)
        elapsed = time.monotonic() - started

        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        if resp.status_code == 201:
            body = resp.json()
            key, issue_id = body["key"], body["id"]
            url = f"{jira.base}/browse/{key}"

            verified = ""
            if args.verify:
                fetched = jira.get_issue(key)
                if fetched and (fetched["fields"]["summary"]
                                == fields["summary"]):
                    verified = "yes"
                else:
                    verified = "MISMATCH" if fetched else "NOT-FOUND"

            state[source_id] = key
            save_state(state_path, state)
            created += 1
            created_keys.append(key)

            line = (f"  OK  row {source_id} -> {key} (id {issue_id})")
            if args.verbose:
                line += f"  {resp.status_code} in {elapsed:.2f}s"
            if verified:
                line += f"  verified={verified}"
            print(line)
            if args.verbose:
                print(f"      {url}")
            if verified in ("MISMATCH", "NOT-FOUND"):
                print(f"      WARNING: post-create verification returned "
                      f"{verified} for {key}")

            append_log(args.csv, {
                "timestamp": timestamp, "source_id": source_id,
                "result": "created", "issue_id": issue_id, "issue_key": key,
                "url": url, "verified": verified, "error": "",
            })
        else:
            error_text = resp.text[:300]
            failed.append((source_id, resp.status_code, error_text))
            print(f"  FAIL row {source_id}: HTTP {resp.status_code} "
                  f"{error_text[:200]}")
            if ("doesn't exist or you don't have permission" in error_text
                    and not scope_hint_shown):
                scope_hint_shown = True
                print(
                    "      NOTE: preflight confirmed the project is visible"
                    + (" and your user CAN create issues"
                       if can_create else "")
                    + ",\n      so this failure is almost certainly a "
                    "READ-ONLY SCOPED API TOKEN.\n"
                    "      Create a new token (classic/unscoped, or scoped "
                    "with write:jira-work)\n"
                    "      at https://id.atlassian.com/manage-profile/"
                    "security/api-tokens\n"
                    "      then update JIRA_API_TOKEN and re-run.")
            append_log(args.csv, {
                "timestamp": timestamp, "source_id": source_id,
                "result": "failed", "issue_id": "", "issue_key": "",
                "url": "", "verified": "",
                "error": f"HTTP {resp.status_code}: {error_text}",
            })

    print(f"\nDone. created={created} skipped={skipped} failed={len(failed)}")
    if created_keys:
        print(f"Created issues: {', '.join(created_keys)}")
        print(f"Full log: {args.csv}.upload-log.csv")
    if unassigned:
        print("Could not resolve a unique assignee for "
              "(left unassigned):")
        for src, name in unassigned:
            print(f"  row {src}: {name!r}")
    if failed:
        print("Failures:")
        for src, status, body in failed:
            print(f"  row {src}: HTTP {status} {body}")
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except requests.exceptions.SSLError:
        print(
            "\nSSL certificate verification failed.\n"
            "This usually means a corporate TLS-inspecting proxy (Zscaler,\n"
            "Netskope, etc.) is re-signing HTTPS traffic with a CA that\n"
            "Python doesn't trust. Fixes, in order of preference:\n"
            "  1. pip install truststore\n"
            "     (the script auto-detects it and uses your OS trust store"
            + ("" if not _TRUSTSTORE else
               " -- truststore IS installed; your OS keychain may be "
               "missing the proxy CA, contact IT")
            + ")\n"
            "  2. Get your company's root CA .pem from IT and run with\n"
            "     --ca-bundle /path/to/corp-ca.pem\n"
            "  3. Or set:  export REQUESTS_CA_BUNDLE=/path/to/corp-ca.pem\n",
            file=sys.stderr,
        )
        sys.exit(2)
    except requests.exceptions.ConnectionError as e:
        print(f"\nCould not connect to Jira: {e}\n"
              "Check JIRA_BASE_URL, your network/VPN, and proxy settings.",
              file=sys.stderr)
        sys.exit(2)
