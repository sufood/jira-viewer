#!/usr/bin/env python3
"""Sync the CSV with Jira. `push` creates issues for blank rows and writes the
Jira Key + URL back; `pull` refreshes content columns from linked issues.

Config (env or .env): JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN,
JIRA_PROJECT_KEY, JIRA_ISSUE_TYPE (default Story).

    python jira_sync.py push --dry-run
    python jira_sync.py push
    python jira_sync.py pull --dry-run
    python jira_sync.py pull
"""

import argparse
import os
import sys
import time

import jira_common as jc

DEFAULT_CSV = "insignia-division-stories-jira-linked.csv"


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


def run_push(jira, csv_path, project_key, issue_type, assign, verify, verbose):
    rows = jc.read_csv(csv_path)
    eligible, linked, inconsistent = classify_push(rows)
    print(f"{len(rows)} rows: {len(eligible)} to create, {len(linked)} "
          f"already linked, {len(inconsistent)} inconsistent (skipped)")
    for r in inconsistent:
        print(f"  WARNING row {r['#']}: only one of Jira Key/URL set "
              f"(key={r.get('Jira Key')!r} url={r.get('Jira URL')!r}); "
              f"not pushed")

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
            print(f"  OK  row {row['#']} -> {key}")
            jc.append_log(str(csv_path), {
                "timestamp": ts, "source_id": row["#"], "result": "created",
                "issue_id": body["id"], "issue_key": key, "url": url,
                "verified": "", "error": ""})
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


def run_pull(jira, csv_path, dry_run, verbose):
    rows = jc.read_csv(csv_path)
    updated, failed = 0, []
    for row in rows:
        if not row.get("Jira URL", "").strip():
            continue                              # nothing linked to pull
        key = _issue_key(row)
        issue = jira.get_issue(key)
        if not issue:
            failed.append(key)
            print(f"  FAIL row {row['#']}: could not fetch {key}")
            continue

        fields = issue["fields"]
        doc = fields.get("description") or {"type": "doc", "version": 1,
                                            "content": []}
        ctx = jc.parse_context_block(doc)
        new_vals = {
            "Opportunity": fields.get("summary", row["Opportunity"]),
            "Description": jc.adf_to_markdown(doc),
        }
        for k in jc.CONTEXT_KEYS:
            if k in ctx:
                new_vals[k] = ctx[k]

        changes = {k: v for k, v in new_vals.items() if row.get(k, "") != v}
        if changes:
            updated += 1
            if verbose or dry_run:
                for k, v in changes.items():
                    print(f"  row {row['#']} {k}: {row.get(k,'')!r} -> {v!r}")
            if not dry_run:
                row.update(new_vals)

    if not dry_run:
        jc.write_csv(csv_path, rows)
    print(f"\nDone. updated={updated} failed={len(failed)}"
          f"{' (dry-run, no write)' if dry_run else ''}")
    return {"updated": updated, "failed": len(failed)}
