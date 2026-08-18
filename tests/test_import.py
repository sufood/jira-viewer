import pytest

import jira_sync
import jira_common as jc


# ---- Jira.search_issues: token-based pagination ---------------------------

def test_search_issues_paginates_with_next_page_token():
    """search_issues must page through the enhanced /search/jql endpoint using
    nextPageToken, POST to the right path, request the given fields, and stop
    when no token comes back."""
    pages = [
        {"issues": [{"key": "AITR-1"}, {"key": "AITR-2"}],
         "nextPageToken": "tok1"},
        {"issues": [{"key": "AITR-3"}]},   # no nextPageToken -> last page
    ]
    calls = []

    class FakeResp:
        status_code = 200
        def __init__(self, body): self._body = body
        def json(self): return self._body

    jira = jc.Jira("https://x.atlassian.net", "e", "t")

    def fake_request(method, url, timeout=None, **kwargs):
        calls.append((method, url, kwargs.get("json")))
        return FakeResp(pages[len(calls) - 1])

    jira.session.request = fake_request
    issues = jira.search_issues("project = AITR", fields=["summary"])

    assert [i["key"] for i in issues] == ["AITR-1", "AITR-2", "AITR-3"]
    assert len(calls) == 2
    method, url, body = calls[0]
    assert method == "POST"
    assert url.endswith("/rest/api/3/search/jql")
    assert body["jql"] == "project = AITR"
    assert body["fields"] == ["summary"]
    assert "nextPageToken" not in body               # first call has no token
    assert calls[1][2]["nextPageToken"] == "tok1"    # second call carries it


def test_search_issues_raises_on_non_200():
    class FakeResp:
        status_code = 400
        text = "bad jql"
        def json(self): return {}

    jira = jc.Jira("https://x.atlassian.net", "e", "t")
    jira.session.request = lambda *a, **k: FakeResp()
    try:
        jira.search_issues("nope", fields=["summary"])
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "400" in str(e)


# ---- run_import: mapping, defaults, round-trip, dry-run -------------------
# These exercise the issue->row mapping only, so kanban capture is off.

class _FakeSearchJira:
    base = "https://x.atlassian.net"
    def __init__(self, issues): self._issues = issues
    def search_issues(self, jql, fields, page_size=100):
        self.jql = jql
        return self._issues


def test_import_defaults_division_and_links(tmp_path):
    """A plain foreign issue (no context block) maps summary/description and
    gets the default Division plus populated Key/URL."""
    issues = [{"key": "AITR-5",
               "fields": {"summary": "Do a thing",
                          "description": jc.markdown_to_adf("## Body\n\nprose")}}]
    csv_path = tmp_path / "out.csv"
    res = jira_sync.run_import(_FakeSearchJira(issues), csv_path, "AITR", None,
                               default_division="N/A", default_ai_fit="",
                               dry_run=False, verbose=False, kanban=False)
    assert res == {"imported": 1, "written": 1}
    row = jc.read_csv(csv_path)[0]
    assert row["#"] == "1"
    assert row["Opportunity"] == "Do a thing"
    assert "Body" in row["Description"]
    assert row["Division"] == "N/A"
    assert row["Jira Key"] == "AITR-5"
    assert row["Jira URL"] == "https://x.atlassian.net/browse/AITR-5"


def test_import_roundtrips_context_block(tmp_path):
    """An issue this toolkit created carries a context block; import recovers
    the real Division/metadata instead of the default."""
    meta = {"Division": "Platform", "AI-fit": "High", "Initiative": "KB",
            "Status": "Funded", "Key people": "Sam", "Systems": "Jira",
            "Themes": "Search", "Summary": "sum"}
    doc = jc.markdown_to_adf("## Real body")
    doc["content"].extend(jc.build_context_block(meta))
    issues = [{"key": "AITR-9", "fields": {"summary": "Titled", "description": doc}}]
    csv_path = tmp_path / "out.csv"
    jira_sync.run_import(_FakeSearchJira(issues), csv_path, "AITR", None,
                         default_division="N/A", default_ai_fit="Medium",
                         dry_run=False, verbose=False, kanban=False)
    row = jc.read_csv(csv_path)[0]
    assert row["Division"] == "Platform"    # context block wins over N/A
    assert row["AI-fit"] == "High"          # and over the --ai-fit default
    assert row["Summary"] == "sum"
    assert row["Jira Key"] == "AITR-9"


def test_import_ai_fit_default_applied_without_context(tmp_path):
    issues = [{"key": "AITR-2", "fields": {"summary": "x",
              "description": jc.markdown_to_adf("body")}}]
    csv_path = tmp_path / "out.csv"
    jira_sync.run_import(_FakeSearchJira(issues), csv_path, "AITR", None,
                         default_division="N/A", default_ai_fit="Medium",
                         dry_run=False, verbose=False, kanban=False)
    row = jc.read_csv(csv_path)[0]
    assert row["AI-fit"] == "Medium"


def test_import_dry_run_writes_nothing(tmp_path):
    issues = [{"key": "AITR-1", "fields": {"summary": "x"}}]
    csv_path = tmp_path / "out.csv"
    res = jira_sync.run_import(_FakeSearchJira(issues), csv_path, "AITR", None,
                              default_division="N/A", default_ai_fit="",
                              dry_run=True, verbose=False, kanban=False)
    assert res == {"imported": 1, "written": 0}
    assert not csv_path.exists()


def test_import_builds_default_jql_from_project():
    fake = _FakeSearchJira([])
    jira_sync.run_import(fake, "unused.csv", "AITR", None,
                         default_division="N/A", default_ai_fit="",
                         dry_run=True, verbose=False, kanban=False)
    assert fake.jql == "project = AITR ORDER BY key ASC"


def test_import_raw_jql_overrides_project():
    fake = _FakeSearchJira([])
    jira_sync.run_import(fake, "unused.csv", "AITR",
                         "project = AITR AND statusCategory != Done",
                         default_division="N/A", default_ai_fit="",
                         dry_run=True, verbose=False, kanban=False)
    assert fake.jql == "project = AITR AND statusCategory != Done"


# ---- kanban capture: Stage (status->column) + Swimlane (per-lane JQL) ------

def test_stage_for_status_maps_and_falls_back():
    cols = [{"name": "IDEAS", "statusIds": ["1", "2"]},
            {"name": "BUILD", "statusIds": ["3"]}]
    assert jc.stage_for_status(cols, "3", "In Progress") == "BUILD"
    assert jc.stage_for_status(cols, "9", "Weird") == "Weird"   # unmapped -> raw
    assert jc.stage_for_status(None, "3", "Raw") == "Raw"       # no board config


class _FakeKanbanJira:
    base = "https://x.atlassian.net"
    columns = [{"name": "IDEAS", "statusIds": ["10"]},
               {"name": "BUILD", "statusIds": ["20"]}]

    def find_board(self, project_key):
        return 6393

    def board_config(self, board_id):
        assert board_id == 6393
        return self.columns

    def search_issues(self, jql, fields, page_size=100):
        if "priority = Highest" in jql:      # Expedite lane membership
            return [{"key": "AITR-2"}]
        if "flagged is not EMPTY" in jql:    # Blocked lane membership
            return [{"key": "AITR-1"}]
        return [                             # the main issue query
            {"key": "AITR-1", "fields": {"summary": "One",
                "status": {"id": "20", "name": "In Build"}}},
            {"key": "AITR-2", "fields": {"summary": "Two",
                "status": {"id": "10", "name": "Idea"}}},
            {"key": "AITR-3", "fields": {"summary": "Three",
                "status": {"id": "20", "name": "In Build"}}},
        ]


def test_import_captures_stage_and_swimlane(tmp_path):
    csv_path = tmp_path / "out.csv"
    jira_sync.run_import(_FakeKanbanJira(), csv_path, "AITR", None,
                         default_division="N/A", default_ai_fit="",
                         dry_run=False, verbose=False,
                         settings_path="no-such-settings.yaml", kanban=True)
    rows = {r["Jira Key"]: r for r in jc.read_csv(csv_path)}
    # status -> board column
    assert rows["AITR-1"]["Stage"] == "BUILD"
    assert rows["AITR-2"]["Stage"] == "IDEAS"
    # swimlane first-match-wins in Expedite->Blocked->default order
    assert rows["AITR-2"]["Swimlane"] == "Expedite"
    assert rows["AITR-1"]["Swimlane"] == "Blocked"
    assert rows["AITR-3"]["Swimlane"] == "Everything Else"


def test_import_stage_falls_back_to_raw_status_without_board():
    """No board id and no board config -> Stage is the raw status name."""
    class NoBoardJira:
        base = "https://x.atlassian.net"
        def find_board(self, project_key): return None
        def board_config(self, board_id): return None
        def search_issues(self, jql, fields, page_size=100):
            if "priority = Highest" in jql or "flagged is not EMPTY" in jql:
                return []
            return [{"key": "AITR-1", "fields": {"summary": "x",
                     "status": {"id": "99", "name": "Doing"}}}]

    import tempfile, os
    d = tempfile.mkdtemp()
    csv_path = os.path.join(d, "out.csv")
    jira_sync.run_import(NoBoardJira(), csv_path, "AITR", None,
                         default_division="N/A", default_ai_fit="",
                         dry_run=False, verbose=False,
                         settings_path="no-such-settings.yaml", kanban=True)
    row = jc.read_csv(csv_path)[0]
    assert row["Stage"] == "Doing"                # raw status name
    assert row["Swimlane"] == "Everything Else"   # no lane matched


# ---- multi-project import: key parsing ------------------------------------

def test_parse_project_keys_splits_on_comma():
    assert jira_sync.parse_project_keys("AITR,AIENG") == ["AITR", "AIENG"]


def test_parse_project_keys_accepts_a_list_from_a_repeated_flag():
    assert jira_sync.parse_project_keys(["AITR", "AIENG"]) == ["AITR", "AIENG"]


def test_parse_project_keys_strips_blanks_and_dedupes_preserving_order():
    assert jira_sync.parse_project_keys(
        [" AITR , , AIENG ", "AITR"]) == ["AITR", "AIENG"]


def test_parse_project_keys_of_nothing_is_empty():
    assert jira_sync.parse_project_keys(None) == []
    assert jira_sync.parse_project_keys("") == []


# ---- multi-project import: JQL scope --------------------------------------

def test_import_builds_in_clause_for_several_projects():
    fake = _FakeSearchJira([])
    jira_sync.run_import(fake, "unused.csv", ["AITR", "AIENG"], None,
                         default_division="N/A", default_ai_fit="",
                         dry_run=True, verbose=False, kanban=False)
    assert fake.jql == "project in (AITR, AIENG) ORDER BY key ASC"


def test_import_single_key_in_a_list_still_uses_equals():
    """One key keeps the simpler `project = KEY` form."""
    fake = _FakeSearchJira([])
    jira_sync.run_import(fake, "unused.csv", ["AITR"], None,
                         default_division="N/A", default_ai_fit="",
                         dry_run=True, verbose=False, kanban=False)
    assert fake.jql == "project = AITR ORDER BY key ASC"


def test_import_swimlane_search_composes_against_multi_project_scope(tmp_path):
    """Lane JQL is AND-ed onto the parenthesised multi-project scope."""
    seen = []

    class LaneSpyJira(_FakeKanbanJira):
        def search_issues(self, jql, fields, page_size=100):
            seen.append(jql)
            return _FakeKanbanJira.search_issues(self, jql, fields, page_size)

    jira_sync.run_import(LaneSpyJira(), tmp_path / "out.csv",
                         ["AITR", "AIENG"], None,
                         default_division="N/A", default_ai_fit="",
                         dry_run=False, verbose=False,
                         settings_path="no-such-settings.yaml", kanban=True)
    assert ("(project in (AITR, AIENG)) AND (priority = Highest)") in seen


# ---- multi-project import: board resolution -------------------------------

class _BoardSpyJira(_FakeKanbanJira):
    """Records which board id was configured and which key find_board saw."""
    def __init__(self):
        self.board_asked = None
        self.find_board_key = None

    def find_board(self, project_key):
        self.find_board_key = project_key
        return 6393

    def board_config(self, board_id):
        self.board_asked = board_id
        return self.columns


def test_import_board_falls_back_to_settings_kanban_board(tmp_path):
    settings = tmp_path / "settings.yaml"
    settings.write_text("kanban:\n  board: 4242\n", encoding="utf-8")
    fake = _BoardSpyJira()
    jira_sync.run_import(fake, tmp_path / "out.csv", ["AITR", "AIENG"], None,
                         default_division="N/A", default_ai_fit="",
                         dry_run=False, verbose=False,
                         settings_path=str(settings), kanban=True)
    assert fake.board_asked == 4242
    assert fake.find_board_key is None       # never asked Jira to discover one


def test_import_explicit_board_beats_settings(tmp_path):
    settings = tmp_path / "settings.yaml"
    settings.write_text("kanban:\n  board: 4242\n", encoding="utf-8")
    fake = _BoardSpyJira()
    jira_sync.run_import(fake, tmp_path / "out.csv", ["AITR"], None,
                         default_division="N/A", default_ai_fit="",
                         dry_run=False, verbose=False, board=99,
                         settings_path=str(settings), kanban=True)
    assert fake.board_asked == 99


def test_import_board_discovery_uses_the_first_key(tmp_path):
    """No --board and no settings board -> discover from the first key only."""
    fake = _BoardSpyJira()
    jira_sync.run_import(fake, tmp_path / "out.csv", ["AITR", "AIENG"], None,
                         default_division="N/A", default_ai_fit="",
                         dry_run=False, verbose=False,
                         settings_path="no-such-settings.yaml", kanban=True)
    assert fake.find_board_key == "AITR"


# ---- multi-project import: preflight --------------------------------------

class _PreflightJira:
    """Sees AITR and WRAP; AIENG and NOPE are invisible."""
    visible = {"AITR": {"key": "AITR", "name": "AI Triage", "issueTypes": []},
               "WRAP": {"key": "WRAP", "name": "Wrap", "issueTypes": []}}

    def check_project(self, key):
        return self.visible.get(key)

    def list_projects(self):
        return [{"key": k} for k in self.visible]


def test_preflight_accepts_a_list_and_checks_every_key(monkeypatch, capsys):
    monkeypatch.setattr(jc, "connect", lambda: _PreflightJira())
    jc.connect_and_preflight(["AITR", "WRAP"], None)
    out = capsys.readouterr().out
    assert "AITR" in out and "WRAP" in out


def test_preflight_reports_every_invisible_key_at_once(monkeypatch):
    monkeypatch.setattr(jc, "connect", lambda: _PreflightJira())
    with pytest.raises(SystemExit) as e:
        jc.connect_and_preflight(["AITR", "AIENG", "NOPE"], None)
    msg = str(e.value)
    assert "AIENG" in msg and "NOPE" in msg          # both, not just the first


def test_preflight_still_accepts_a_bare_string_key(monkeypatch):
    monkeypatch.setattr(jc, "connect", lambda: _PreflightJira())
    assert jc.connect_and_preflight("AITR", None) is not None
