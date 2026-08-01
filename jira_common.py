#!/usr/bin/env python3
"""Shared helpers for the Jira ⇄ CSV toolkit: env, CSV I/O, ADF, Jira client."""

import csv
import os

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
