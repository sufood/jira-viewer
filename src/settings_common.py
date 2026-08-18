#!/usr/bin/env python3
"""Settings + division derivation for the whole-page-from-files regenerate.

- load_settings: read settings.yaml (dependency-light; {} when absent).
- derive_divisions: build the Divisions-CSV rows from the stories CSV, with
  Systems/Themes unioned per division and colour/tagline/background from
  settings (auto-colour otherwise).
- merge_settings_into_data: overlay header/hub/legend onto the app data object.
- apply_people: overlay division key people (from people.csv) onto departments.
"""

import os

import yaml

import jira_common as jc   # reuse split_multi (";"-split) — DRY

# Auto-colour palette = the app's own 13 division colours, so new divisions
# look native. Assigned deterministically by roster index (cycles if >13).
PALETTE = ["#3f7c8c", "#c1743a", "#6b6ca3", "#4a8f6d", "#3b6ea5", "#b0567f",
           "#a8484a", "#8a6d3b", "#2f8f8f", "#7a5aa8", "#b98a3c", "#6f8c3e",
           "#bd5f6b"]

# Exact Divisions-CSV header the app's Upload CSV expects.
DIVISION_COLUMNS = ["Division", "Systems", "Themes", "Tagline", "Background",
                    "Colour"]


def load_settings(path="settings.yaml"):
    """Parse settings.yaml into a dict; {} if the file doesn't exist."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _union(seen, cell):
    """Append the ';'-split values of `cell` to list `seen`, dedup, keep order."""
    for v in jc.split_multi(cell):
        if v not in seen:
            seen.append(v)


def derive_divisions(story_rows, settings):
    """Return (division_rows, unmatched_setting_names).

    Roster = distinct `Division` values in first-appearance order. Systems and
    Themes are the deduped union across each division's stories. Colour/Tagline/
    Background come from settings['divisions'][name]; colour auto-assigns from
    PALETTE by roster index when not overridden.
    """
    order, systems, themes = [], {}, {}
    for r in story_rows:
        d = (r.get("Division") or "").strip()
        if not d:
            continue
        if d not in systems:
            order.append(d)
            systems[d], themes[d] = [], []
        _union(systems[d], r.get("Systems", ""))
        _union(themes[d], r.get("Themes", ""))

    overrides = settings.get("divisions") or {}
    rows = []
    for i, d in enumerate(order):
        o = overrides.get(d) or {}
        rows.append({
            "Division": d,
            "Systems": "; ".join(systems[d]),
            "Themes": "; ".join(themes[d]),
            "Tagline": o.get("tagline", ""),
            "Background": o.get("background", ""),
            "Colour": o.get("colour") or PALETTE[i % len(PALETTE)],
        })
    unmatched = [k for k in overrides if k not in systems]
    return rows, unmatched


# Current app defaults (from the bundle's migrate() seed) — the starting point
# a user edits. Values chosen to match what the app ships with today.
_DEFAULT_INTRO = ("In this view, click any division to fan out its cards — "
                  "problem areas, AI-fit, the people engaged, gaps and next steps.")


def build_starter_settings(division_rows):
    """Assemble a fully-populated settings dict from the app's current defaults
    plus per-division overrides taken from an exported Divisions CSV."""
    return {
        "header": {
            "company": "Insignia Financial",
            "title": "AI Strategy Value Realisation",
            "intro": _DEFAULT_INTRO,
        },
        "hub": {
            "name": "AI Strategy",
            "tagline": "Enterprise-wide AI strategy programme — March 2026",
            "url": "https://ifl.atlassian.net/jira/software/c/projects/AITR/boards/6393",
        },
        "legend": {
            "title": "AI-fit rating",
            "levels": [
                {"label": "High", "color": "#e0674c"},
                {"label": "Medium-High", "color": "#e3a24b"},
                {"label": "Medium", "color": "#5aa9a0"},
                {"label": "Medium-Low", "color": "#7d8ca3"},
            ],
        },
        "divisions": {
            r["Division"]: {"colour": r.get("Colour", ""),
                            "tagline": r.get("Tagline", ""),
                            "background": r.get("Background", "")}
            for r in division_rows
        },
    }


def merge_settings_into_data(d, settings):
    """Overlay settings onto the app data object `d`, in place. Only keys present
    in settings are touched (never blanks out). settings['legend'] -> d['fitRating']."""
    hdr = settings.get("header")
    if hdr and isinstance(d.get("header"), dict):
        for k in ("company", "title", "intro"):
            if k in hdr:
                d["header"][k] = hdr[k]
    hub = settings.get("hub")
    if hub and isinstance(d.get("hub"), dict):
        for k in ("name", "tagline", "url"):
            if k in hub:
                d["hub"][k] = hub[k]
    leg = settings.get("legend")
    if leg:
        fr = d.setdefault("fitRating", {})
        if "title" in leg:
            fr["title"] = leg["title"]
        if "levels" in leg:
            fr["levels"] = [{"label": l["label"], "color": l["color"]}
                            for l in leg["levels"]]
    kb = settings.get("kanban")
    if kb:
        lanes = kb.get("swimlanes") or []
        d["kanban"] = {
            "stages": list(kb.get("stages") or []),
            "swimlanes": {l["name"]: l.get("colour", "") for l in lanes
                          if l.get("name")},
            "defaultLane": next((l["name"] for l in lanes if not l.get("jql")),
                                "Everything Else"),
        }
    return d


PEOPLE_COLUMNS = ["Division", "Name", "Role", "Relevance"]


def apply_people(d, people_rows):
    """Fully authoritative: set every department's `people` from people_rows,
    grouped by Division (row order preserved). A department with no rows gets an
    empty list. Blank Division/Name rows are skipped. Returns (d, unmatched),
    where unmatched lists Division values with no matching department. Mutates d."""
    by_div = {}
    for r in people_rows:
        div = (r.get("Division") or "").strip()
        name = (r.get("Name") or "").strip()
        if not div or not name:
            continue
        by_div.setdefault(div, []).append({
            "name": name,
            "role": (r.get("Role") or "").strip(),
            "relevance": (r.get("Relevance") or "").strip(),
        })
    deps = d.get("departments") or []
    dep_names = {dep.get("name") for dep in deps}
    for dep in deps:
        dep["people"] = by_div.get(dep.get("name"), [])
    unmatched = [k for k in by_div if k not in dep_names]
    return d, unmatched
