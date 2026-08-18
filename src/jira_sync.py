#!/usr/bin/env python3
"""Sync the CSV with Jira. `push` creates issues for blank rows and writes the
Jira Key + URL back; `pull` refreshes content columns from linked issues;
`import` reads every issue in a project (or raw JQL) into a fresh CSV.

Config (env or .env): JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN,
JIRA_PROJECT_KEY, JIRA_ISSUE_TYPE (default Story).

    python jira_sync.py push --dry-run
    python jira_sync.py push
    python jira_sync.py pull --dry-run
    python jira_sync.py pull
    python jira_sync.py import --project AITR --csv ai-topics.csv --dry-run
    python jira_sync.py import --project AITR --csv ai-topics.csv
"""

import argparse
import os
import re
import sys
import time

import jira_common as jc

DEFAULT_CSV = "insignia-division-stories-jira-linked.csv"

# Query-swimlane rules used by `import` to reconstruct lane membership (Jira's
# API doesn't expose query-swimlane JQL). First match wins, top-down; the lane
# with no jql is the catch-all default. Overridden by settings.yaml kanban.swimlanes.
DEFAULT_SWIMLANES = [
    {"name": "Expedite", "jql": "priority = Highest", "colour": "#e3a24b"},
    {"name": "Blocked", "jql": "flagged is not EMPTY", "colour": "#c0504d"},
    {"name": "Everything Else", "jql": None, "colour": "#8a94a2"},
]


def load_swimlanes(settings_path):
    """kanban.swimlanes from settings.yaml when PyYAML + the file are present,
    else the built-in defaults. Keeps push/pull free of a hard YAML dependency
    (the import path soft-imports yaml only when needed)."""
    try:
        import yaml
    except ImportError:
        return DEFAULT_SWIMLANES
    if not settings_path or not os.path.exists(settings_path):
        return DEFAULT_SWIMLANES
    with open(settings_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    lanes = (data.get("kanban") or {}).get("swimlanes")
    return lanes or DEFAULT_SWIMLANES


def load_defaults(settings_path):
    """The `defaults:` block from settings.yaml (fill-blank ladder config), or
    the built-in DEFAULTS_FALLBACK when PyYAML/the file/the block are absent.
    apply_fallbacks shallow-merges this over the built-ins, so a partial block
    (e.g. just a `component_division` map) is fine."""
    try:
        import yaml
    except ImportError:
        return dict(jc.DEFAULTS_FALLBACK)
    if not settings_path or not os.path.exists(settings_path):
        return dict(jc.DEFAULTS_FALLBACK)
    with open(settings_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    block = data.get("defaults")
    return block if isinstance(block, dict) else dict(jc.DEFAULTS_FALLBACK)


def _tally_fill(counter, filled):
    """Accumulate {column: {source: count}} across rows for the fill report."""
    for col, source in filled.items():
        counter.setdefault(col, {}).setdefault(source, 0)
        counter[col][source] += 1


def _print_fill_report(counter, dry_run=False):
    """One-line summary of blanks filled by the no-context-block ladder."""
    if not counter:
        return
    parts = []
    for col in jc.CONTEXT_KEYS:
        if col in counter:
            total = sum(counter[col].values())
            srcs = ", ".join(f"{s} {n}" for s, n in sorted(counter[col].items()))
            parts.append(f"{col}×{total} ({srcs})")
    tag = " (dry-run)" if dry_run else ""
    print(f"Filled blank fields with no/partial context block{tag}: "
          + "; ".join(parts))


def confirm(question):
    """Ask `question` as a y/N prompt whose default is No: only an explicit
    'y'/'yes' returns True. A non-interactive stdin (pipe, cron, CI) declines
    rather than blocking or silently proceeding — pass --yes to write there."""
    prompt = f"{question} [y/N] "
    if not sys.stdin or not sys.stdin.isatty():
        print(prompt)
        print("  stdin is not interactive; declining. Re-run with --yes to proceed.")
        return False
    try:
        answer = input(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in ("y", "yes")


def classify_push(rows):
    """Split rows into (eligible, linked, inconsistent) by Key/URL state."""
    eligible, linked, inconsistent = [], [], []
    for r in rows:
        has_key = bool(r.get("Jira Key", "").strip())
        has_url = bool(r.get("Jira URL", "").strip())
        if not has_key and not has_url:
            eligible.append(r)
        elif has_key and has_url:
            linked.append(r)
        else:
            inconsistent.append(r)
    return eligible, linked, inconsistent


def run_push(jira, csv_path, project_key, issue_type, assign, verify, verbose,
             require_confirm=False):
    rows = jc.read_csv(csv_path)
    eligible, linked, inconsistent = classify_push(rows)
    print(f"{len(rows)} rows: {len(eligible)} to create, {len(linked)} "
          f"already linked, {len(inconsistent)} inconsistent (skipped)")
    for r in inconsistent:
        print(f"  WARNING row {r['#']}: only one of Jira Key/URL set "
              f"(key={r.get('Jira Key')!r} url={r.get('Jira URL')!r}); "
              f"not pushed")

    # push writes NEW issues to Jira — an irreversible external change — so gate
    # it behind an explicit y/N (default N) when confirmation is requested.
    if require_confirm and eligible:
        if not confirm(f"push will create {len(eligible)} new issue(s) in "
                       f"Jira project {project_key}. Proceed?"):
            print("Aborted — no issues created.")
            return {"created": 0, "failed": 0,
                    "inconsistent": len(inconsistent), "aborted": True}

    created, failed = 0, []
    for row in eligible:
        payload = {"fields": {
            "project": {"key": project_key},
            "issuetype": {"name": issue_type},
            "summary": row["Opportunity"][:255],
            "description": jc.build_description(row),
            "labels": jc.build_labels(row),
        }}
        if assign:
            first = jc.split_multi(row["Key people"])
            acct = jira.find_account_id(first[0]) if first else None
            if acct:
                payload["fields"]["assignee"] = {"accountId": acct}

        if verbose:
            print(f"  row {row['#']}: {payload['fields']['summary'][:70]}  "
                  f"labels={payload['fields']['labels']}")

        resp = jira.create_issue(payload)
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        if resp.status_code == 201:
            body = resp.json()
            key = body["key"]
            url = f"{jira.base}/browse/{key}"
            row["Jira Key"] = key
            row["Jira URL"] = url
            jc.write_csv(csv_path, rows)     # save after each create
            created += 1

            verified = ""
            if verify:
                fetched = jira.get_issue(key)
                if fetched and (fetched["fields"].get("summary")
                                == payload["fields"]["summary"]):
                    verified = "yes"
                else:
                    verified = "MISMATCH" if fetched else "NOT-FOUND"

            line = f"  OK  row {row['#']} -> {key}"
            if verified:
                line += f"  verified={verified}"
            print(line)
            if verified in ("MISMATCH", "NOT-FOUND"):
                print(f"      WARNING: post-create verification returned "
                      f"{verified} for {key}")
            jc.append_log(str(csv_path), {
                "timestamp": ts, "source_id": row["#"], "result": "created",
                "issue_id": body["id"], "issue_key": key, "url": url,
                "verified": verified, "error": ""})
        else:
            err = resp.text[:300]
            failed.append((row["#"], resp.status_code, err))
            print(f"  FAIL row {row['#']}: HTTP {resp.status_code} {err[:160]}")
            jc.append_log(str(csv_path), {
                "timestamp": ts, "source_id": row["#"], "result": "failed",
                "issue_id": "", "issue_key": "", "url": "", "verified": "",
                "error": f"HTTP {resp.status_code}: {err}"})

    print(f"\nDone. created={created} failed={len(failed)} "
          f"inconsistent={len(inconsistent)}")
    return {"created": created, "failed": len(failed),
            "inconsistent": len(inconsistent)}


def _issue_key(row):
    key = row.get("Jira Key", "").strip()
    if key:
        return key
    url = row.get("Jira URL", "").strip()
    return url.rstrip("/").split("/")[-1] if url else ""


def run_pull(jira, csv_path, dry_run, verbose, require_confirm=False,
             defaults=None):
    rows = jc.read_csv(csv_path)
    failed = []
    fill_counter = {}                             # {column: {source: count}}
    # First pass: fetch each linked issue and work out the changes WITHOUT
    # mutating the rows yet, so the confirmation gate can see the whole picture
    # (and we never fetch an issue twice).
    planned = []                                  # [(row, new_vals, changes)]
    for row in rows:
        if not row.get("Jira URL", "").strip():
            continue                              # nothing linked to pull
        key = _issue_key(row)
        issue = jira.get_issue(key)
        if not issue:
            failed.append(key)
            print(f"  FAIL row {row['#']}: could not fetch {key}")
            continue

        # Shared mapping: summary -> Opportunity, and (only when the API
        # returned a description) body + context-block metadata. Falls back to
        # the current row so an absent field never blanks the CSV.
        new_vals = jc.issue_content(issue, current=row)
        # No/partial context block: fill still-BLANK metadata from the ladder
        # (labels/native Jira fields/defaults) without overwriting anything.
        if defaults is not None:
            prospective = {**row, **new_vals}
            filled = jc.apply_fallbacks(prospective, issue, defaults)
            if filled:
                _tally_fill(fill_counter, filled)
                for col in filled:
                    new_vals[col] = prospective[col]
        changes = {k: v for k, v in new_vals.items() if row.get(k, "") != v}
        if changes:
            planned.append((row, new_vals, changes))

    updated = len(planned)
    # An "overwrite" replaces a NON-EMPTY existing cell; filling a blank is not
    # a loss of existing data and so never needs confirming.
    overwrites = [(row, k) for row, _, changes in planned
                  for k in changes if row.get(k, "").strip()]

    if verbose or dry_run:
        for row, _, changes in planned:
            for k, v in changes.items():
                print(f"  row {row['#']} {k}: {row.get(k, '')!r} -> {v!r}")

    if dry_run:
        _print_fill_report(fill_counter, dry_run=True)
        print(f"\nDone. updated={updated} failed={len(failed)} (dry-run, no write)")
        return {"updated": updated, "failed": len(failed)}

    # Existing values would be overwritten -> gate behind an explicit y/N
    # (default N). Filling only-blank cells writes straight through.
    if require_confirm and overwrites:
        if not verbose:                           # show what's at stake once
            print(f"{len(overwrites)} existing value(s) would be overwritten:")
            for row, _, changes in planned:
                for k in changes:
                    if row.get(k, "").strip():
                        print(f"  row {row['#']} {k}: {row.get(k, '')!r} -> "
                              f"{changes[k]!r}")
        if not confirm(f"pull will overwrite {len(overwrites)} existing "
                       f"value(s) in {os.path.basename(str(csv_path))} with "
                       f"Jira content. Proceed?"):
            print("Aborted — no changes written.")
            return {"updated": 0, "failed": len(failed), "aborted": True}

    for row, new_vals, _ in planned:
        row.update(new_vals)
    jc.write_csv(csv_path, rows)
    _print_fill_report(fill_counter)
    print(f"\nDone. updated={updated} failed={len(failed)}")
    return {"updated": updated, "failed": len(failed)}


def run_import(jira, csv_path, project_key, jql, default_division,
               default_ai_fit, dry_run, verbose, board=None,
               settings_path="settings.yaml", kanban=True, defaults=None):
    """Read every issue matching a project key (or raw JQL) into a fresh
    jira-linked CSV. Each issue becomes one row: summary -> Opportunity, body ->
    Description, and — for issues this toolkit created — the context block round-
    trips Division / Initiative / AI-fit / ... back into their columns.

    For issues with NO context block: when `defaults` is given, the fill-blank
    ladder (`jc.apply_fallbacks`) infers Division/Initiative/Key people/Systems/
    Themes/AI-fit/Status from Jira labels and native fields, then applies static
    defaults; `--division`/`--ai-fit` override the static Division/AI-fit. When
    `defaults` is None (e.g. `--no-fill`), it keeps the legacy behaviour: just
    `default_division` (so the row stays on the map) and optional `default_ai_fit`.
    Jira Key / Jira URL are populated, so a later `pull` keeps the CSV in sync."""
    # CLI --division/--ai-fit override the static defaults in the ladder.
    eff_defaults = None
    if defaults is not None:
        eff_defaults = dict(defaults)
        if default_division:
            eff_defaults["division"] = default_division
        if default_ai_fit:
            eff_defaults["ai_fit"] = default_ai_fit
    fill_counter = {}
    # `query` is the issue search (verbatim raw JQL, or project + default order);
    # `scope` is the same filter WITHOUT any ORDER BY, so it can be AND-composed
    # with each swimlane's JQL.
    if jql:
        query = jql
        scope = re.split(r"\s+ORDER\s+BY\s+", jql, maxsplit=1, flags=re.I)[0]
    else:
        scope = f"project = {project_key}"
        query = f"{scope} ORDER BY key ASC"
    print(f"JQL: {query}")

    # Kanban structure: board columns give status->Stage; per-lane JQL searches
    # reconstruct Swimlane membership (first match wins, Jira's query-swimlane
    # semantics). Both are skipped when kanban=False.
    columns, lane_sets, default_lane = None, [], ""
    if kanban:
        board_id = board or (jira.find_board(project_key) if project_key else None)
        if board_id:
            columns = jira.board_config(board_id)
            if columns:
                print(f"Board {board_id}: {len(columns)} columns "
                      f"({', '.join(c['name'] for c in columns)})")
            else:
                print(f"  warning: board {board_id} configuration unreadable; "
                      f"Stage falls back to raw status names")
        else:
            print("  notice: no board id (pass --board or set kanban.board in "
                  "settings.yaml); Stage falls back to raw status names")
        swimlanes = load_swimlanes(settings_path)
        default_lane = next((l["name"] for l in swimlanes if not l.get("jql")),
                            swimlanes[-1]["name"] if swimlanes else "")
        for lane in swimlanes:
            if lane.get("jql"):
                keys = {i.get("key") for i in jira.search_issues(
                    f"({scope}) AND ({lane['jql']})", fields=["status"])}
                lane_sets.append((lane["name"], keys))
                print(f"  swimlane {lane['name']!r}: {len(keys)} issue(s)")

    # The fill ladder reads labels + native Jira fields, so request them too.
    fields = ["summary", "description"]
    if eff_defaults is not None:
        fields += ["labels", "assignee", "components", "parent"]
    if kanban:
        fields += ["status"]
    issues = jira.search_issues(query, fields=fields)
    print(f"{len(issues)} issue(s) returned")

    rows = []
    for i, issue in enumerate(issues, 1):
        key = issue.get("key", "")
        row = {c: "" for c in jc.COLUMNS}
        row["#"] = str(i)
        # Content (incl. any context-block metadata) is authoritative.
        row.update(jc.issue_content(issue))
        if eff_defaults is not None:
            # Fill still-blank metadata from the ladder (labels/native fields,
            # then static defaults incl. Division -> N/A). Fill-blank-only, so
            # the context block above always wins.
            _tally_fill(fill_counter, jc.apply_fallbacks(row, issue, eff_defaults))
        else:
            # Legacy behaviour (--no-fill): default Division + optional AI-fit.
            if not row.get("Division", "").strip():
                row["Division"] = default_division or "N/A"
            if default_ai_fit and not row.get("AI-fit", "").strip():
                row["AI-fit"] = default_ai_fit
        row["Jira Key"] = key
        row["Jira URL"] = f"{jira.base}/browse/{key}" if key else ""
        if kanban:
            status = issue.get("fields", {}).get("status") or {}
            row["Stage"] = jc.stage_for_status(
                columns, status.get("id", ""), status.get("name", ""))
            swim = default_lane
            for name, keys in lane_sets:
                if key in keys:
                    swim = name
                    break
            row["Swimlane"] = swim
        rows.append(row)
        if verbose or dry_run:
            extra = (f"  stage={row['Stage']!r} lane={row['Swimlane']!r}"
                     if kanban else "")
            print(f"  {key}: {row['Opportunity'][:60]}  "
                  f"div={row['Division']!r}{extra}")

    if dry_run:
        print(f"\nDRY-RUN import: {len(rows)} row(s) would be written to "
              f"{csv_path} (no write)")
        return {"imported": len(rows), "written": 0}

    jc.write_csv(csv_path, rows)
    print(f"\nDone. imported={len(rows)} -> {csv_path}")
    return {"imported": len(rows), "written": len(rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_push = sub.add_parser("push", help="create Jira issues for blank rows")
    p_pull = sub.add_parser("pull", help="refresh columns from linked issues")
    p_import = sub.add_parser(
        "import", help="read all issues in a project/JQL into a new CSV")
    for p in (p_push, p_pull, p_import):
        p.add_argument("--csv", default=DEFAULT_CSV)
        p.add_argument("--dry-run", action="store_true")
        p.add_argument("-v", "--verbose", action="store_true")
        p.add_argument("--ca-bundle", metavar="PATH")
    # push creates issues in Jira; pull can overwrite existing CSV values. Both
    # ask for a y/N (default N) first; --yes proceeds without asking (unattended).
    for p in (p_push, p_pull):
        p.add_argument(
            "-y", "--yes", action="store_true",
            help="skip the confirmation prompt and proceed (for unattended runs)")
    p_push.add_argument("--assign", action="store_true",
                        help="set first Key person as assignee when unambiguous")
    p_push.add_argument("--verify", action="store_true",
                        help="GET each created issue back to confirm it exists")
    p_import.add_argument(
        "--project", metavar="KEY",
        help="project key to import, e.g. AITR (default: JIRA_PROJECT_KEY)")
    p_import.add_argument(
        "--jql", metavar="QUERY",
        help="raw JQL, overrides --project (e.g. 'project = AITR AND "
             "statusCategory != Done')")
    p_import.add_argument(
        "--division", default="N/A", metavar="NAME",
        help="Division assigned to imported rows without one (default: N/A; "
             "blank-Division rows are dropped from the map, so keep a value)")
    p_import.add_argument(
        "--ai-fit", default="", metavar="LEVEL",
        help="optional default AI-fit for imported rows (e.g. Medium)")
    p_import.add_argument(
        "--board", type=int, metavar="ID",
        help="Agile board id for Stage mapping (default: first board on the "
             "project). Its column order becomes the kanban stages.")
    p_import.add_argument(
        "--settings", default="settings.yaml", metavar="PATH",
        help="settings.yaml to read kanban.swimlanes from (default: settings.yaml)")
    p_import.add_argument(
        "--no-kanban", action="store_true",
        help="skip Stage/Swimlane capture (issues only)")
    args = parser.parse_args()

    jc.load_dotenv(".env")
    if args.ca_bundle:
        os.environ["REQUESTS_CA_BUNDLE"] = args.ca_bundle

    project_key = os.environ.get("JIRA_PROJECT_KEY", "PROJ")
    issue_type = os.environ.get("JIRA_ISSUE_TYPE", "Story")

    if args.dry_run and args.cmd == "push":
        rows = jc.read_csv(args.csv)
        eligible, linked, inconsistent = classify_push(rows)
        print(f"DRY-RUN push: {len(eligible)} would be created, "
              f"{len(linked)} linked, {len(inconsistent)} inconsistent")
        for r in eligible:
            payload = {"summary": r["Opportunity"][:255],
                       "labels": jc.build_labels(r)}
            print(f"  row {r['#']}: {payload['summary']}  "
                  f"labels={payload['labels']}")
        for r in inconsistent:
            print(f"  WARNING row {r['#']}: inconsistent Key/URL; not pushed")
        return 0

    if args.cmd == "import":
        # A raw --jql query needs no project key; otherwise fall back to
        # --project then JIRA_PROJECT_KEY. Import reads issues, so it needs auth
        # (and project visibility when a key is used) but no create permission
        # or a particular issue type.
        import_key = args.project or os.environ.get("JIRA_PROJECT_KEY")
        if not import_key and not args.jql:
            sys.exit("import needs --project KEY or --jql QUERY "
                     "(or JIRA_PROJECT_KEY in .env).")
        if import_key:
            jira = jc.connect_and_preflight(import_key, None,
                                            require_create=False)
        else:
            jira = jc.connect()
        res = run_import(jira, args.csv, import_key, args.jql,
                         default_division=args.division,
                         default_ai_fit=args.ai_fit,
                         dry_run=args.dry_run, verbose=args.verbose,
                         board=args.board, settings_path=args.settings,
                         kanban=not args.no_kanban)
        return 0 if res["imported"] else 1

    if not os.environ.get("JIRA_PROJECT_KEY"):
        sys.exit('JIRA_PROJECT_KEY not set (env or .env).')

    jira = jc.connect_and_preflight(project_key, issue_type,
                                    require_create=(args.cmd == "push"))
    if args.cmd == "push":
        res = run_push(jira, args.csv, project_key, issue_type,
                       assign=args.assign, verify=args.verify,
                       verbose=args.verbose, require_confirm=not args.yes)
        return 1 if res["failed"] else 0
    res = run_pull(jira, args.csv, dry_run=args.dry_run, verbose=args.verbose,
                   require_confirm=not args.yes)
    return 1 if res["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
