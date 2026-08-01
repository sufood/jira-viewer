import jira_sync
import jira_common as jc


def test_pull_updates_columns_from_issue(tmp_path):
    src = {c: "" for c in jc.COLUMNS}
    src.update({"#": "1", "Opportunity": "OLD", "Description": "old",
                "Division": "OLD", "AI-fit": "OLD", "Key people": "OLD",
                "Systems": "OLD", "Themes": "OLD", "Summary": "OLD",
                "Jira Key": "ABC-1", "Jira URL": "https://x/browse/ABC-1"})
    csv_path = tmp_path / "d.csv"
    jc.write_csv(csv_path, [src])

    fresh = {"Division": "NEWDIV", "AI-fit": "Medium", "Key people": "NewPerson",
             "Systems": "NewSys", "Themes": "NewTheme", "Summary": "NewSum"}
    doc = jc.markdown_to_adf("## New body\n\n- point")
    doc["content"].extend(jc.build_context_block(fresh))

    class FakeJira:
        def get_issue(self, key):
            assert key == "ABC-1"
            return {"fields": {"summary": "NEW TITLE", "description": doc}}

    result = jira_sync.run_pull(FakeJira(), csv_path, dry_run=False, verbose=False)
    assert result["updated"] == 1
    row = jc.read_csv(csv_path)[0]
    assert row["Opportunity"] == "NEW TITLE"
    assert row["Division"] == "NEWDIV"
    assert row["Summary"] == "NewSum"
    assert "New body" in row["Description"]
    assert row["Jira Key"] == "ABC-1"          # link columns untouched


def test_pull_skips_rows_without_url(tmp_path):
    src = {c: "" for c in jc.COLUMNS}
    src.update({"#": "1", "Opportunity": "keep"})
    csv_path = tmp_path / "d.csv"
    jc.write_csv(csv_path, [src])

    class FakeJira:
        def get_issue(self, key):
            raise AssertionError("should not be called")

    result = jira_sync.run_pull(FakeJira(), csv_path, dry_run=False, verbose=False)
    assert result["updated"] == 0
    assert jc.read_csv(csv_path)[0]["Opportunity"] == "keep"
