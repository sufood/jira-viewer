import csv
import pytest

COLUMNS = [
    "#", "Division", "Initiative", "Opportunity", "AI-fit", "Status",
    "Key people", "Systems", "Themes", "Summary", "Description",
    "Jira Key", "Jira URL", "Stage", "Swimlane",
]


@pytest.fixture
def sample_row():
    return {
        "#": "1",
        "Division": "Portfolio & FAO",
        "Initiative": "Knowledge Bases",
        "Opportunity": "Unit Pricing Control — the S.U.E. agent",
        "AI-fit": "High",
        "Status": "Funded",
        "Key people": "Chris Page",
        "Systems": "Unified Data Platform; Copilot; Jira",
        "Themes": "Anomaly detection; Reconciliation & matching",
        "Summary": "Move to predictive, risk-weighted alerting.",
        "Description": "## Problem\n\n**Core problem:** Tolerance-based control.\n\n- Retrospective\n- High volume",
        "Jira Key": "",
        "Jira URL": "",
        "Stage": "",
        "Swimlane": "",
    }


@pytest.fixture
def write_csv_file(tmp_path):
    def _write(rows, name="data.csv"):
        path = tmp_path / name
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS, quoting=csv.QUOTE_ALL)
            w.writeheader()
            for r in rows:
                w.writerow(r)
        return path
    return _write
