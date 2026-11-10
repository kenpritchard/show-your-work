"""Review evidence: finding a test's source and the diff it relates to, against a real temp git repo."""

import shutil
import subprocess
from dataclasses import replace

import pytest

from show_your_work import evidence as ev
from show_your_work.project import load_project

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

JAVA_BASE = """package com.example;

public class CalcTest {
    @Test
    void addsNumbers() {
        assertEquals(2, add(1, 1));
    }

    @Test
    void subtracts() {
        assertEquals(0, sub(1, 1));
    }
}
"""

JAVA_HEAD = """package com.example;

public class CalcTest {
    @Test
    void addsNumbers() {
        assertEquals(2, add(1, 1));
    }

    @Test
    void subtracts() {
        assertEquals(0, sub(1, 1));
        assertEquals(-1, sub(0, 1)); // { brace in a comment
    }

    @ParameterizedTest
    @ValueSource(ints = {1, 2})
    void dividesByOne(int n) {
        String s = "}";
        assertEquals(n, div(n, 1));
    }
}
"""

PY_TEST = """import pytest


def test_old():
    assert 1


def test_new_case():
    x = 2
    assert x == 2
"""


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "app"
    jdir = root / "src" / "test" / "java" / "com" / "example"
    jdir.mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "main.py").write_text("def f():\n    return 1\n")
    (jdir / "CalcTest.java").write_text(JAVA_BASE)
    (root / "tests" / "test_app.py").write_text("import pytest\n\n\ndef test_old():\n    assert 1\n")
    (root / "criteria.md").write_text("- [R1] adds\n")
    (root / "syw.toml").write_text('criteria_file = "criteria.md"\ntracked = ["src/**/*"]\nbase = "main"\n')
    git(root, "init", "-q", "-b", "main")
    git(root, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base")
    git(root, "checkout", "-q", "-b", "fix")
    (jdir / "CalcTest.java").write_text(JAVA_HEAD)
    (root / "tests" / "test_app.py").write_text(PY_TEST)
    (root / "src" / "main.py").write_text("def f():\n    return 2\n")
    return root


def test_split_test_id_strips_parameter_suffixes():
    assert ev.split_test_id("com.x.FooTest::bar(int)[3]") == ("com.x.FooTest", "bar")
    assert ev.split_test_id("tests.test_a::test_b[case-1]") == ("tests.test_a", "test_b")
    assert ev.split_test_id("plain") == ("", "plain")


def test_new_parameterized_java_test(repo):
    r = ev.test_evidence(load_project(repo), "com.example.CalcTest::dividesByOne(int)[2]")
    assert r["file"] == "src/test/java/com/example/CalcTest.java"
    assert r["method_found"] and r["status"] == "new test"
    assert r["source"].lstrip().startswith("@ParameterizedTest") and r["source"].rstrip().endswith("}")
    assert "+    void dividesByOne(int n) {" in r["diff"]
    assert "subtracts" not in r["diff"]  # trimmed to this method, not the whole hunk


def test_changed_java_test_ignores_braces_in_strings_and_comments(repo):
    r = ev.test_evidence(load_project(repo), "com.example.CalcTest::subtracts")
    assert r["status"] == "changed test" and r["diff_scope"] == "method"
    assert "+        assertEquals(-1, sub(0, 1));" in r["diff"]
    assert len(r["source"].splitlines()) == 5  # @Test .. closing brace, whole method


def test_unchanged_test_next_to_changes_is_unchanged(repo):
    r = ev.test_evidence(load_project(repo), "com.example.CalcTest::addsNumbers")
    assert r["status"].startswith("unchanged") and r["diff"] is None


def test_python_test_found_by_module_path(repo):
    r = ev.test_evidence(load_project(repo), "tests.test_app::test_new_case")
    assert r["file"] == "tests/test_app.py" and r["status"] == "new test"
    assert r["source"].startswith("def test_new_case") and "assert x == 2" in r["source"]


def test_unknown_test_and_missing_method(repo):
    r = ev.test_evidence(load_project(repo), "com.nope.Gone::x")
    assert r["file"] is None and r["notes"]
    r = ev.test_evidence(load_project(repo), "com.example.CalcTest::notThere")
    assert not r["method_found"] and "whole file" in r["notes"][0]


def test_change_evidence_lists_files_and_production_diff(repo):
    c = ev.change_evidence(load_project(repo))
    assert {f["path"] for f in c["files"]} == {"src/main.py", "src/test/java/com/example/CalcTest.java",
                                              "tests/test_app.py"}
    assert c["production_files"] == ["src/main.py"]
    assert "+    return 2" in c["diff"]


def test_no_base_and_bad_base(repo):
    p = load_project(repo)
    r = ev.test_evidence(replace(p, base=""), "com.example.CalcTest::subtracts")
    assert r["source"] and r["diff"] is None and "no base" in " ".join(r["notes"])
    r = ev.test_evidence(replace(p, base="--output=/tmp/x"), "com.example.CalcTest::subtracts")
    assert r["diff"] is None and "not a valid git ref" in " ".join(r["notes"])


def test_not_a_git_repo(tmp_path):
    root = tmp_path / "plain"
    root.mkdir()
    (root / "criteria.md").write_text("- [R1] x\n")
    (root / "syw.toml").write_text('criteria_file = "criteria.md"\n')
    r = ev.test_evidence(load_project(root), "a.B::c")
    assert "not a git repository" in " ".join(r["notes"])
