import csv
import jira_common as jc


def test_columns_constant_exact_order():
    assert jc.COLUMNS == [
        "#", "Division", "Initiative", "Opportunity", "AI-fit", "Status",
        "Key people", "Systems", "Themes", "Summary", "Description",
        "Jira Key", "Jira URL", "Stage", "Swimlane",
    ]


def test_read_csv_strips_bom(write_csv_file, sample_row):
    path = write_csv_file([sample_row])
    rows = jc.read_csv(path)
    assert list(rows[0].keys())[0] == "#"          # BOM stripped from first key
    assert rows[0]["Division"] == "Portfolio & FAO"


def test_write_csv_roundtrips_bom_and_quoting(write_csv_file, sample_row, tmp_path):
    src = write_csv_file([sample_row])
    rows = jc.read_csv(src)
    out = tmp_path / "out.csv"
    jc.write_csv(out, rows)
    raw = out.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")          # BOM preserved
    text = raw.decode("utf-8-sig")
    assert text.splitlines()[0] == (                # every field quoted
        '"#","Division","Initiative","Opportunity","AI-fit","Status",'
        '"Key people","Systems","Themes","Summary","Description",'
        '"Jira Key","Jira URL","Stage","Swimlane"'
    )
    assert jc.read_csv(out) == rows                 # data round-trips


def test_load_dotenv_does_not_override_os_env(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("JIRA_PROJECT_KEY=FROMFILE\nJIRA_EMAIL=file@x.com\n")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "FROMOS")
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    jc.load_dotenv(env)
    import os
    assert os.environ["JIRA_PROJECT_KEY"] == "FROMOS"   # OS wins
    assert os.environ["JIRA_EMAIL"] == "file@x.com"     # file fills the gap
