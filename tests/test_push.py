import pytest

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


def test_push_aborts_when_confirmation_declined(monkeypatch, tmp_path):
    """require_confirm + a 'no' answer must NOT write to Jira and must leave the
    CSV untouched."""
    rows = _make_rows()

    class FakeJira:
        base = "https://x.atlassian.net"
        def create_issue(self, payload):
            raise AssertionError("must not create when the user declines")

    monkeypatch.setattr(jira_sync, "confirm", lambda q: False)
    csv_path = tmp_path / "d.csv"
    jira_sync.jc.write_csv(csv_path, rows)
    result = jira_sync.run_push(FakeJira(), csv_path, "PROJ", "Story",
                                assign=False, verify=False, verbose=False,
                                require_confirm=True)
    assert result["created"] == 0
    assert result.get("aborted") is True
    # the blank row stays blank — nothing was written back
    assert jira_sync.jc.read_csv(csv_path)[0]["Jira Key"] == ""


def test_push_proceeds_when_confirmation_accepted(monkeypatch, tmp_path):
    rows = _make_rows()

    class FakeResp:
        status_code = 201
        def json(self):
            return {"key": "ABC-1", "id": "1001"}

    class FakeJira:
        base = "https://x.atlassian.net"
        def create_issue(self, payload):
            return FakeResp()

    asked = []
    monkeypatch.setattr(jira_sync, "confirm",
                        lambda q: asked.append(q) or True)
    csv_path = tmp_path / "d.csv"
    jira_sync.jc.write_csv(csv_path, rows)
    result = jira_sync.run_push(FakeJira(), csv_path, "PROJ", "Story",
                                assign=False, verify=False, verbose=False,
                                require_confirm=True)
    assert result["created"] == 1
    assert len(asked) == 1                    # confirmation was requested once


def test_confirm_defaults_to_no(monkeypatch):
    """Blank/'n' answer -> False; only an explicit y/yes -> True."""
    class TTY:
        def isatty(self): return True
    monkeypatch.setattr(jira_sync.sys, "stdin", TTY())
    for answer, expected in [("", False), ("n", False), ("no", False),
                             ("y", True), ("Y", True), ("yes", True)]:
        monkeypatch.setattr("builtins.input", lambda prompt, a=answer: a)
        assert jira_sync.confirm("go?") is expected


def test_confirm_declines_non_interactive(monkeypatch):
    """A non-TTY stdin declines rather than proceeding silently."""
    class NotTTY:
        def isatty(self): return False
    monkeypatch.setattr(jira_sync.sys, "stdin", NotTTY())
    assert jira_sync.confirm("go?") is False


def test_push_verify_confirms_created_issue(tmp_path):
    rows = _make_rows()

    class FakeResp:
        status_code = 201
        def json(self):
            return {"key": "ABC-1", "id": "1001"}

    class FakeJira:
        base = "https://x.atlassian.net"
        got = []
        def create_issue(self, payload):
            return FakeResp()
        def get_issue(self, key):
            self.got.append(key)
            return {"fields": {"summary": "Alpha"}}   # matches Opportunity

    fake = FakeJira()
    csv_path = tmp_path / "d.csv"
    jira_sync.jc.write_csv(csv_path, rows)
    result = jira_sync.run_push(fake, csv_path, "PROJ", "Story",
                                assign=False, verify=True, verbose=False)
    assert result["created"] == 1
    assert fake.got == ["ABC-1"]      # --verify actually fetched the issue back


# ---- push targets exactly one project -------------------------------------

def test_push_rejects_a_comma_separated_project_key():
    """import may span projects; push creates issues, so it needs exactly one.
    A comma in JIRA_PROJECT_KEY must fail loudly, not create issues in a
    project literally named 'AITR,AIENG'."""
    with pytest.raises(SystemExit) as e:
        jira_sync.single_project_key("AITR,AIENG")
    assert "AITR,AIENG" in str(e.value)


def test_single_project_key_passes_a_lone_key_through():
    assert jira_sync.single_project_key(" AITR ") == "AITR"
