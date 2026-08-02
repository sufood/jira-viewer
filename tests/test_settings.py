import settings_common as sc


def _story(div, systems, themes):
    return {"Division": div, "Systems": systems, "Themes": themes}


def test_derive_divisions_roster_first_appearance_order():
    rows = [_story("B", "s1", "t1"), _story("A", "s2", "t2"),
            _story("B", "s3", "t1")]
    divs, unmatched = sc.derive_divisions(rows, {})
    assert [d["Division"] for d in divs] == ["B", "A"]      # first-appearance
    assert unmatched == []


def test_derive_divisions_unions_systems_themes_dedup():
    rows = [_story("A", "Sys1; Sys2", "Th1"),
            _story("A", "Sys2; Sys3", "Th1; Th2")]
    divs, _ = sc.derive_divisions(rows, {})
    d = divs[0]
    assert d["Systems"] == "Sys1; Sys2; Sys3"              # deduped, order kept
    assert d["Themes"] == "Th1; Th2"


def test_derive_divisions_applies_overrides_and_auto_colour():
    rows = [_story("A", "s", "t"), _story("B", "s", "t")]
    settings = {"divisions": {"A": {"colour": "#abcdef",
                                    "tagline": "TA", "background": "BG"}}}
    divs, unmatched = sc.derive_divisions(rows, settings)
    a = next(d for d in divs if d["Division"] == "A")
    b = next(d for d in divs if d["Division"] == "B")
    assert a["Colour"] == "#abcdef" and a["Tagline"] == "TA" and a["Background"] == "BG"
    assert b["Colour"] == sc.PALETTE[1]                    # auto by roster index
    assert b["Tagline"] == "" and b["Background"] == ""
    assert unmatched == []


def test_derive_divisions_warns_unmatched_settings_division():
    rows = [_story("A", "s", "t")]
    divs, unmatched = sc.derive_divisions(rows, {"divisions": {"Ghost": {}}})
    assert [d["Division"] for d in divs] == ["A"]
    assert unmatched == ["Ghost"]


def test_load_settings_missing_returns_empty(tmp_path):
    assert sc.load_settings(tmp_path / "nope.yaml") == {}


def test_load_settings_partial(tmp_path):
    p = tmp_path / "settings.yaml"
    p.write_text('header:\n  company: "X"\n')
    s = sc.load_settings(p)
    assert s == {"header": {"company": "X"}}


def test_merge_settings_overlays_only_present_keys():
    d = {"header": {"company": "old", "title": "keep", "intro": "keepi"},
         "hub": {"id": "hub", "name": "old", "tagline": "old", "url": "old"},
         "fitRating": {"title": "old", "levels": [{"label": "L", "color": "#111"}]}}
    settings = {"header": {"company": "NEW"},
                "hub": {"url": "http://new"},
                "legend": {"title": "Fit", "levels": [{"label": "Hi", "color": "#222"}]}}
    out = sc.merge_settings_into_data(d, settings)
    assert out["header"] == {"company": "NEW", "title": "keep", "intro": "keepi"}
    assert out["hub"]["url"] == "http://new" and out["hub"]["id"] == "hub"
    assert out["fitRating"] == {"title": "Fit", "levels": [{"label": "Hi", "color": "#222"}]}


def test_merge_settings_empty_is_noop():
    d = {"header": {"company": "c"}}
    assert sc.merge_settings_into_data(d, {}) == {"header": {"company": "c"}}


def test_build_starter_settings_from_division_rows():
    div_rows = [{"Division": "A", "Systems": "s", "Themes": "t",
                 "Tagline": "TA", "Background": "BA", "Colour": "#111"}]
    s = sc.build_starter_settings(div_rows)
    assert s["header"]["company"] == "Insignia Financial"
    assert s["hub"]["url"].startswith("https://ifl.atlassian.net/")
    assert s["legend"]["levels"][0] == {"label": "High", "color": "#e0674c"}
    assert s["divisions"]["A"] == {"colour": "#111", "tagline": "TA",
                                   "background": "BA"}


def _person(div, name, role="r", rel="x"):
    return {"Division": div, "Name": name, "Role": role, "Relevance": rel}


def test_apply_people_sets_people_per_department():
    d = {"departments": [{"name": "A", "people": [{"name": "old"}]},
                         {"name": "B", "people": []}]}
    rows = [_person("A", "Ann", "Lead", "does X"),
            _person("A", "Bob"), _person("B", "Cara")]
    out, unmatched = sc.apply_people(d, rows)
    a = next(x for x in out["departments"] if x["name"] == "A")
    assert a["people"] == [{"name": "Ann", "role": "Lead", "relevance": "does X"},
                           {"name": "Bob", "role": "r", "relevance": "x"}]
    assert unmatched == []


def test_apply_people_is_authoritative_empties_absent_department():
    d = {"departments": [{"name": "A", "people": [{"name": "keep?"}]},
                         {"name": "B", "people": [{"name": "gone"}]}]}
    out, _ = sc.apply_people(d, [_person("A", "Ann")])
    b = next(x for x in out["departments"] if x["name"] == "B")
    assert b["people"] == []                       # not in file -> emptied


def test_apply_people_reports_unmatched_division():
    d = {"departments": [{"name": "A", "people": []}]}
    _, unmatched = sc.apply_people(d, [_person("Ghost", "X")])
    assert unmatched == ["Ghost"]


def test_apply_people_skips_blank_division_or_name():
    d = {"departments": [{"name": "A", "people": [{"name": "old"}]}]}
    rows = [_person("", "NoDiv"), _person("A", ""), _person("A", "RealPerson")]
    out, _ = sc.apply_people(d, rows)
    a = out["departments"][0]
    assert [p["name"] for p in a["people"]] == ["RealPerson"]
