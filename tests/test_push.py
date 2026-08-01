import jira_sync


def _make_rows():
    base = {c: "" for c in jira_sync.jc.COLUMNS}
    both_blank = {**base, "#": "1", "Opportunity": "Alpha",
                  "Division": "D", "AI-fit": "High", "Key people": "P",
                  "Systems": "S", "Themes": "T", "Summary": "Sum",
                  "Description": "body"}
    both_filled = {**base, "#": "2", "Opportunity": "Beta",
                   "Jira Key": "ABC-9", "Jira URL": "https://x/browse/ABC-9"}
    inconsistent = {**base, "#": "3", "Opportunity": "Gamma",
                    "Jira Key": "ABC-7", "Jira URL": ""}
    return [both_blank, both_filled, inconsistent]


def test_classify_rows():
    rows = _make_rows()
    eligible, linked, inconsistent = jira_sync.classify_push(rows)
    assert [r["#"] for r in eligible] == ["1"]
    assert [r["#"] for r in linked] == ["2"]
    assert [r["#"] for r in inconsistent] == ["3"]


def test_push_writes_key_and_url_back(monkeypatch, tmp_path):
    rows = _make_rows()

    class FakeResp:
        status_code = 201
        def json(self):
            return {"key": "ABC-1", "id": "1001"}

    class FakeJira:
        base = "https://x.atlassian.net"
        def create_issue(self, payload):
            assert payload["fields"]["summary"] == "Alpha"   # Opportunity = title
            assert payload["fields"]["issuetype"]["name"] == "Story"
            return FakeResp()

    csv_path = tmp_path / "d.csv"
    jira_sync.jc.write_csv(csv_path, rows)
    result = jira_sync.run_push(FakeJira(), csv_path, "PROJ", "Story",
                                assign=False, verify=False, verbose=False)
    assert result["created"] == 1
    assert result["inconsistent"] == 1
    saved = jira_sync.jc.read_csv(csv_path)
    row1 = next(r for r in saved if r["#"] == "1")
    assert row1["Jira Key"] == "ABC-1"
    assert row1["Jira URL"] == "https://x.atlassian.net/browse/ABC-1"
