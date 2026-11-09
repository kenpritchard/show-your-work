"""The four-column status model, end to end through the service (temp SQLite, temp project)."""

import sqlite3

import pytest

from show_your_work.project import ProjectError
from show_your_work.service import Service

PASS_ALL = b"""<testsuite>
  <testcase classname="t" name="test_a"/>
  <testcase classname="t" name="test_b"/>
</testsuite>"""

FAIL_B = b"""<testsuite>
  <testcase classname="t" name="test_a"/>
  <testcase classname="t" name="test_b"><failure message="boom"/></testcase>
</testsuite>"""

ONLY_A = b"""<testsuite><testcase classname="t" name="test_a"/></testsuite>"""


@pytest.fixture
def proj(tmp_path):
    root = tmp_path / "app"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("x = 1\n")
    (root / "criteria.md").write_text("- [R1] first\n- [R2] second\n- [R3] third\n")
    (root / "syw.toml").write_text('criteria_file = "criteria.md"\ntracked = ["src/**/*.py"]\n')
    return root


@pytest.fixture
def svc(tmp_path):
    return Service(sqlite3.connect(tmp_path / "syw.db", check_same_thread=False))


def write(proj, name, data):
    (proj / name).write_bytes(data)
    return name


def rows(board):
    return {r["id"]: r for r in board["requirements"]}


def test_fresh_project_everything_untested(svc, proj):
    b = rows(svc.board(proj))
    assert set(b) == {"R1", "R2", "R3"}
    for r in b.values():
        assert (r["coverage"], r["outcome"], r["freshness"], r["review"]) == (
            "none", "not run", "unknown", "none")


def test_link_then_import_pass_and_fail(svc, proj):
    svc.link(proj, "R1", ["t::test_a"], by="agent")
    svc.link(proj, "R2", ["t::test_b"], by="agent")
    svc.import_report(proj, write(proj, "r.xml", FAIL_B))
    b = rows(svc.board(proj))
    assert (b["R1"]["coverage"], b["R1"]["outcome"], b["R1"]["freshness"]) == ("linked", "pass", "current")
    assert b["R2"]["outcome"] == "fail"
    assert b["R3"]["coverage"] == "none"  # the untested requirement stays visible
    assert svc.board(proj)["summary"]["untested"] == 1


def test_linked_test_missing_from_latest_run_is_not_run(svc, proj):
    svc.link(proj, "R2", ["t::test_b"], by="agent")
    svc.import_report(proj, write(proj, "r.xml", ONLY_A))
    assert rows(svc.board(proj))["R2"]["outcome"] == "not run"


def test_worst_outcome_wins_across_linked_tests(svc, proj):
    svc.link(proj, "R1", ["t::test_a", "t::test_b"], by="agent")
    svc.import_report(proj, write(proj, "r.xml", FAIL_B))
    assert rows(svc.board(proj))["R1"]["outcome"] == "fail"


def test_runs_are_append_only_and_latest_wins(svc, proj):
    svc.link(proj, "R2", ["t::test_b"], by="agent")
    first = svc.import_report(proj, write(proj, "r1.xml", FAIL_B))
    second = svc.import_report(proj, write(proj, "r2.xml", PASS_ALL))
    assert first["run_id"] != second["run_id"]
    assert rows(svc.board(proj))["R2"]["outcome"] == "pass"
    assert [r["run_id"] for r in svc.runs(proj)] == [second["run_id"], first["run_id"]]
    assert svc.run_detail(proj, first["run_id"])["results"][1]["outcome"] == "fail"


def test_code_change_makes_results_stale(svc, proj):
    svc.link(proj, "R1", ["t::test_a"], by="agent")
    svc.import_report(proj, write(proj, "r.xml", PASS_ALL))
    (proj / "src" / "app.py").write_text("x = 2\n")
    r1 = rows(svc.board(proj))["R1"]
    assert (r1["outcome"], r1["freshness"]) == ("pass", "stale")


def test_human_accept_and_it_goes_stale_on_code_change(svc, proj):
    svc.link(proj, "R1", ["t::test_a"], by="agent")
    svc.import_report(proj, write(proj, "r.xml", PASS_ALL))
    svc.review(proj, "R1", "accepted", note="looks right", by="human:desktop")
    assert rows(svc.board(proj))["R1"]["review"] == "accepted"
    (proj / "src" / "app.py").write_text("x = 3\n")
    assert rows(svc.board(proj))["R1"]["review"] == "stale"


def test_review_goes_stale_when_wording_changes(svc, proj):
    svc.review(proj, "R1", "rejected", note="no test", by="human:slash")
    assert rows(svc.board(proj))["R1"]["review"] == "rejected"
    (proj / "criteria.md").write_text("- [R1] first, reworded\n- [R2] second\n- [R3] third\n")
    assert rows(svc.board(proj))["R1"]["review"] == "stale"


def test_import_does_not_touch_reviews(svc, proj):
    svc.review(proj, "R1", "accepted", by="human:desktop")
    svc.import_report(proj, write(proj, "r.xml", PASS_ALL))
    assert rows(svc.board(proj))["R1"]["review"] == "accepted"


def test_review_rejects_bad_decision_and_unknown_requirement(svc, proj):
    with pytest.raises(ValueError):
        svc.review(proj, "R1", "approved-by-vibes", by="human:desktop")
    with pytest.raises(KeyError):
        svc.review(proj, "R9", "accepted", by="human:desktop")


def test_link_unknown_requirement_is_refused(svc, proj):
    with pytest.raises(KeyError):
        svc.link(proj, "R9", ["t::test_a"], by="agent")


def test_unlink(svc, proj):
    svc.link(proj, "R1", ["t::test_a"], by="agent")
    svc.unlink(proj, "R1", ["t::test_a"])
    assert rows(svc.board(proj))["R1"]["coverage"] == "none"


@pytest.mark.parametrize("bad", ["../outside.xml", "/etc/hosts"])
def test_import_path_must_be_inside_project(svc, proj, bad):
    (proj.parent / "outside.xml").write_bytes(PASS_ALL)
    with pytest.raises(ProjectError, match="inside the project"):
        svc.import_report(proj, bad)


def test_import_records_provenance_and_report_hash(svc, proj):
    out = svc.import_report(proj, write(proj, "r.xml", PASS_ALL), provenance="external")
    run = svc.runs(proj)[0]
    assert run["provenance"] == "external"
    assert len(run["report_sha256"]) == 64
    assert out["tests"] == 2


def test_projects_are_isolated(svc, proj, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    (other / "criteria.md").write_text("- [R1] other\n")
    (other / "syw.toml").write_text('criteria_file = "criteria.md"\ntracked = []\n')
    svc.link(proj, "R1", ["t::test_a"], by="agent")
    assert rows(svc.board(other))["R1"]["coverage"] == "none"


def test_board_lists_links_to_requirements_that_no_longer_exist(svc, proj):
    svc.link(proj, "R3", ["t::test_a"], by="agent")
    (proj / "criteria.md").write_text("- [R1] first\n- [R2] second\n")
    assert svc.board(proj)["orphan_links"] == [{"requirement": "R3", "test_id": "t::test_a"}]


def test_import_a_folder_of_reports_as_one_run(svc, proj):
    d = proj / "reports"
    d.mkdir()
    (d / "TEST-a.xml").write_bytes(b'<testsuite><testcase classname="t" name="test_a"/></testsuite>')
    (d / "TEST-b.xml").write_bytes(b'<testsuite><testcase classname="t" name="test_b"><failure message="boom"/></testcase></testsuite>')
    (d / "notes.txt").write_text("ignored")
    svc.link(proj, "R1", ["t::test_a"], by="agent")
    svc.link(proj, "R2", ["t::test_b"], by="agent")
    out = svc.import_report(proj, "reports")
    assert out["tests"] == 2 and len(svc.runs(proj)) == 1
    b = rows(svc.board(proj))
    assert (b["R1"]["outcome"], b["R2"]["outcome"]) == ("pass", "fail")


def test_bad_file_in_report_folder_names_the_file(svc, proj):
    d = proj / "reports"
    d.mkdir()
    (d / "TEST-bad.xml").write_bytes(b"<testsuite><testcase")
    with pytest.raises(ValueError, match="TEST-bad.xml"):
        svc.import_report(proj, "reports")


def test_empty_report_folder_is_an_error(svc, proj):
    (proj / "reports").mkdir()
    with pytest.raises(ProjectError, match="no .xml"):
        svc.import_report(proj, "reports")


def test_report_older_than_code_is_freshness_unknown(svc, proj):
    import os
    write(proj, "r.xml", PASS_ALL)
    old = (proj / "src" / "app.py").stat().st_mtime - 3600
    os.utime(proj / "r.xml", (old, old))
    svc.link(proj, "R1", ["t::test_a"], by="agent")
    out = svc.import_report(proj, "r.xml")
    assert out["warnings"] and "older" in out["warnings"][0]
    r1 = rows(svc.board(proj))["R1"]
    assert (r1["outcome"], r1["freshness"]) == ("pass", "unknown")


def test_folder_import_skips_non_junit_xml(svc, proj):
    d = proj / "failsafe-reports"
    d.mkdir()
    (d / "TEST-a.xml").write_bytes(b'<testsuite><testcase classname="t" name="test_a"/></testsuite>')
    (d / "failsafe-summary.xml").write_bytes(b"<failsafe-summary result='0'><completed>1</completed></failsafe-summary>")
    out = svc.import_report(proj, "failsafe-reports")
    assert out["tests"] == 1
    assert any("failsafe-summary.xml" in w for w in out["warnings"])


def test_folder_with_only_non_junit_xml_is_an_error(svc, proj):
    d = proj / "r"
    d.mkdir()
    (d / "summary.xml").write_bytes(b"<summary/>")
    with pytest.raises(ProjectError, match="no JUnit reports"):
        svc.import_report(proj, "r")


def test_single_non_junit_file_is_still_an_error(svc, proj):
    write(proj, "s.xml", b"<failsafe-summary/>")
    with pytest.raises(ValueError, match="unexpected root"):
        svc.import_report(proj, "s.xml")
