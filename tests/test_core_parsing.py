"""Criteria file, JUnit XML, project config and file fingerprint parsing."""

import pytest

from show_your_work.criteria import parse_criteria
from show_your_work.junit import MAX_REPORT_BYTES, parse_junit
from show_your_work.project import ProjectError, fingerprint, load_project


# ---------- criteria ----------

def test_parses_requirement_lines_and_ignores_other_text():
    text = """# Tip calculator

Some intro prose.
- [R1] Tip is 15% by default
* [R2]   Splits the bill between people
- not a requirement
- [R3] Rounds to the nearest cent
"""
    crit = parse_criteria(text)
    assert [c.id for c in crit] == ["R1", "R2", "R3"]
    assert crit[1].text == "Splits the bill between people"


def test_duplicate_requirement_ids_are_rejected():
    with pytest.raises(ValueError, match="R1"):
        parse_criteria("- [R1] one\n- [R1] two\n")


def test_digest_ignores_whitespace_but_not_wording():
    a = parse_criteria("- [R1] Tip is  15%\n")[0]
    b = parse_criteria("- [R1]   Tip is 15%  \n")[0]
    c = parse_criteria("- [R1] Tip is 18%\n")[0]
    assert a.digest == b.digest
    assert a.digest != c.digest


def test_empty_criteria_file_is_an_error():
    with pytest.raises(ValueError, match="no requirements"):
        parse_criteria("just prose\n")


# ---------- junit ----------

PYTEST_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="4">
  <testcase classname="tests.test_tip" name="test_default_tip" time="0.01"/>
  <testcase classname="tests.test_tip" name="test_split">
    <failure message="assert 33.0 == 33.33">long traceback</failure>
  </testcase>
  <testcase classname="tests.test_tip" name="test_round"><error message="ZeroDivisionError"/></testcase>
  <testcase classname="tests.test_tip" name="test_currency"><skipped message="not yet"/></testcase>
</testsuite></testsuites>"""


def test_junit_outcomes_and_ids():
    results = {r.test_id: r for r in parse_junit(PYTEST_XML)}
    assert results["tests.test_tip::test_default_tip"].outcome == "pass"
    assert results["tests.test_tip::test_split"].outcome == "fail"
    assert results["tests.test_tip::test_split"].message == "assert 33.0 == 33.33"
    assert results["tests.test_tip::test_round"].outcome == "error"
    assert results["tests.test_tip::test_currency"].outcome == "skipped"


def test_junit_single_testsuite_root_and_nested_suites():
    xml = b"""<testsuite name="outer"><testsuite name="inner">
      <testcase name="lonely"/></testsuite></testsuite>"""
    assert [r.test_id for r in parse_junit(xml)] == ["lonely"]


def test_malformed_xml_gives_clear_error():
    with pytest.raises(ValueError, match="not valid JUnit XML"):
        parse_junit(b"<testsuite><testcase")


def test_entity_expansion_is_refused():
    bomb = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;">]>
<testsuite><testcase name="&lol2;"/></testsuite>"""
    with pytest.raises(ValueError, match="unsafe"):
        parse_junit(bomb)


def test_oversized_report_is_refused():
    with pytest.raises(ValueError, match="too large"):
        parse_junit(b" " * (MAX_REPORT_BYTES + 1))


def test_report_without_testcases_is_an_error():
    with pytest.raises(ValueError, match="no test cases"):
        parse_junit(b"<testsuites/>")


# ---------- project config + fingerprint ----------

def _project(tmp_path, toml=None):
    (tmp_path / "criteria.md").write_text("- [R1] works\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x = 1\n")
    (tmp_path / "syw.toml").write_text(
        toml or 'criteria_file = "criteria.md"\ntracked = ["src/**/*.py"]\n'
    )
    return tmp_path


def test_load_project(tmp_path):
    proj = load_project(_project(tmp_path))
    assert proj.root == tmp_path.resolve()
    assert [c.id for c in proj.criteria] == ["R1"]
    assert proj.tracked == ["src/**/*.py"]


def test_missing_config_is_a_project_error(tmp_path):
    with pytest.raises(ProjectError, match="syw.toml"):
        load_project(tmp_path)


@pytest.mark.parametrize("bad", ['"../outside.md"', '"/etc/passwd"'])
def test_criteria_file_must_stay_inside_project(tmp_path, bad):
    root = _project(tmp_path, f"criteria_file = {bad}\ntracked = []\n")
    with pytest.raises(ProjectError, match="inside the project"):
        load_project(root)


def test_tracked_patterns_must_stay_inside_project(tmp_path):
    root = _project(tmp_path, 'criteria_file = "criteria.md"\ntracked = ["../**/*"]\n')
    with pytest.raises(ProjectError, match="inside the project"):
        load_project(root)


def test_fingerprint_changes_when_a_tracked_file_changes(tmp_path):
    proj = load_project(_project(tmp_path))
    before = fingerprint(proj)
    (tmp_path / "src" / "app.py").write_text("x = 2\n")
    after = fingerprint(proj)
    assert before.digest != after.digest
    assert before.file_count == after.file_count == 1


def test_fingerprint_ignores_untracked_files(tmp_path):
    proj = load_project(_project(tmp_path))
    before = fingerprint(proj)
    (tmp_path / "notes.txt").write_text("hi")
    assert fingerprint(proj).digest == before.digest


def test_fingerprint_skips_symlinks_out_of_project(tmp_path):
    proj = load_project(_project(tmp_path))
    outside = tmp_path.parent / "outside_secret.py"
    outside.write_text("secret")
    (tmp_path / "src" / "link.py").symlink_to(outside)
    assert fingerprint(proj).file_count == 1
