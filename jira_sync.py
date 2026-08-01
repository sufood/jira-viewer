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
