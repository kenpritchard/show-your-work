"""Regression tests for the catalog review of 9c6edcff (NousResearch/hermes-agent#153051)."""

import ast
import os
import re
import sys
import time
from pathlib import Path

import pytest

from show_your_work import evidence as ev
from show_your_work.criteria import parse_criteria, strip_comments
from show_your_work.project import MAX_CRITERIA_BYTES, ProjectError, load_project

ROOT = Path(__file__).resolve().parents[1]
SHIPPED = [p for p in ROOT.rglob("*.py")
           if not {"tests", ".venv", "node_modules", "__pycache__", "examples"} & set(p.relative_to(ROOT).parts)]


# ---------- 1. every third-party import is declared ----------

def _declared() -> set[str]:
    text = (ROOT / "plugin.yaml").read_text()
    block = re.search(r"^python_dependencies:\n((?:\s+- .+\n?)+)", text, re.M)
    assert block, "plugin.yaml must declare python_dependencies"
    names = re.findall(r"-\s*[\"']?([A-Za-z0-9_.-]+)", block.group(1))
    return {n.lower().replace("-", "_") for n in names}


# Supplied by the Hermes process the plugin runs in, not installed for it.
PROVIDED_BY_HERMES = {"agent", "plugins", "fastapi"}


def test_every_third_party_import_is_declared():
    imported = set()
    for path in SHIPPED:
        for node in ast.walk(ast.parse(path.read_text(), str(path))):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.add(node.module.split(".")[0])
    third_party = {m for m in imported if m not in sys.stdlib_module_names} - PROVIDED_BY_HERMES
    assert third_party == {"defusedxml"}, f"new third-party import, declare it in plugin.yaml: {third_party}"
    assert third_party <= _declared()


def test_defusedxml_pin_is_compatible_with_hermes_core():
    assert re.search(r'"defusedxml>=0\.7\.1,<0\.8"', (ROOT / "plugin.yaml").read_text())


# ---------- 2. export refuses a planted symlink ----------

def _project(tmp_path):
    root = tmp_path / "app"
    root.mkdir()
    (root / "criteria.md").write_text("- [R1] first\n")
    (root / "syw.toml").write_text('criteria_file = "criteria.md"\ntracked = []\n')
    return root


@pytest.fixture
def handlers(tmp_path):
    import importlib
    import importlib.util
    import sqlite3

    spec = importlib.util.spec_from_file_location(
        "syw_review_fixes_pkg", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    h = importlib.import_module("syw_review_fixes_pkg.handlers")
    svc = importlib.import_module("syw_review_fixes_pkg.show_your_work.service")
    h._service = svc.Service(sqlite3.connect(tmp_path / "db.sqlite", check_same_thread=False))
    yield h
    h._service = None


@pytest.mark.skipif(sys.platform == "win32", reason="Symlinks require elevated privileges on Windows")
def test_export_refuses_symlink_and_leaves_target_untouched(handlers, tmp_path):
    root = _project(tmp_path)
    victim = tmp_path / "outside.txt"
    victim.write_text("original")
    (root / "show-your-work-review.md").symlink_to(victim)
    # The plugin package is loaded under its own name, so use its ProjectError, not the top-level one.
    with pytest.raises(handlers.ProjectError, match="symlink"):
        handlers.write_export(root)
    assert victim.read_text() == "original"
    assert not list(root.glob(".show-your-work-review.md.*")), "temp file left behind"


@pytest.mark.skipif(sys.platform == "win32", reason="Symlinks require elevated privileges on Windows")
def test_slash_export_reports_symlink_refusal(handlers, tmp_path, monkeypatch):
    root = _project(tmp_path)
    (root / "show-your-work-review.md").symlink_to(tmp_path / "elsewhere.md")
    monkeypatch.setattr(handlers, "_session_root", lambda: root)
    assert "symlink" in handlers.slash("export")
    assert not (tmp_path / "elsewhere.md").exists()


def test_export_replaces_existing_file_atomically(handlers, tmp_path):
    root = _project(tmp_path)
    out = root / "show-your-work-review.md"
    out.write_text("stale")
    assert handlers.write_export(root) == out
    assert out.read_text().startswith("#") and not out.is_symlink()
    if sys.platform != "win32":
        assert (out.stat().st_mode & 0o777) == 0o644
    assert sorted(p.name for p in root.iterdir()) == ["criteria.md", "show-your-work-review.md", "syw.toml"]


@pytest.mark.skipif(sys.platform == "win32", reason="Symlinks require elevated privileges on Windows")
def test_symlink_swapped_in_after_the_check_is_replaced_not_followed(handlers, tmp_path, monkeypatch):
    """os.replace swaps the directory entry, so a race after the is_symlink() check still can't redirect."""
    root = _project(tmp_path)
    victim = tmp_path / "outside.txt"
    victim.write_text("original")
    real_replace = os.replace

    def plant_then_replace(src, dst):
        Path(dst).symlink_to(victim)
        real_replace(src, dst)

    monkeypatch.setattr(handlers.os, "replace", plant_then_replace)
    out = handlers.write_export(root)
    assert victim.read_text() == "original"
    assert not out.is_symlink() and out.read_text().startswith("#")


# ---------- 3. criteria parsing stays linear ----------

@pytest.mark.parametrize("text", [
    "- [B1] a <!-- c --> b\n<!--\n- [B2] gone\n-->\n- [B3] kept",
    "<!-- one --><!-- two -->- [R1] x",
    "- [R1] x <!-- unclosed",
    "<!-- a <!-- nested --> - [R1] tail -->",
    "--> <!-- -->",
    "<!---->- [R1] x",
    "",
])
def test_strip_comments_matches_the_old_regex(text):
    assert strip_comments(text) == re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def _seconds(fn):
    t = time.perf_counter()
    fn()
    return time.perf_counter() - t


def test_many_unclosed_comment_markers_parse_quickly():
    hostile = "<!--" * 200_000 + "\n- [R1] still found\n"  # ~0.8 MB; the old regex took minutes
    found = None

    def run():
        nonlocal found
        found = parse_criteria(hostile)

    assert _seconds(run) < 1.0
    assert [c.id for c in found] == ["R1"]


def test_long_run_of_spaces_in_one_line_parses_quickly():
    hostile = "- [R1] a" + " " * 1_000_000 + "b\n"
    found = None

    def run():
        nonlocal found
        found = parse_criteria(hostile)

    assert _seconds(run) < 1.0
    assert found[0].text == "a b"


def test_requirement_with_no_text_is_ignored():
    with pytest.raises(ValueError, match="no requirements"):
        parse_criteria("- [R1]   \n- [R2]\n")


def test_oversized_criteria_file_is_refused(tmp_path):
    root = _project(tmp_path)
    with (root / "criteria.md").open("a") as fh:
        fh.write("x" * MAX_CRITERIA_BYTES)
    with pytest.raises(ProjectError, match="too large"):
        load_project(root)


# ---------- 4. (recommended) classnames can't probe outside the project ----------

@pytest.mark.parametrize("cls", [
    "/etc/passwd.py", "../outside.py", "tests/../../outside.py", "..\\outside.py", "C:\\x\\y.py",
    "a./etc/outside", "../outside",
])
def test_classnames_naming_paths_outside_are_refused_before_probing(tmp_path, cls, monkeypatch):
    root = _project(tmp_path)
    (tmp_path / "outside.py").write_text("def test_x():\n    pass\n")
    probed = []
    real = Path.is_file
    monkeypatch.setattr(Path, "is_file", lambda self: probed.append(self) or real(self))
    assert ev.find_test_file(load_project(root), f"{cls}::test_x") is None
    outside = [p for p in probed if not p.resolve().is_relative_to(root.resolve())]
    assert outside == [], f"probed outside the project: {outside}"


@pytest.mark.skipif(sys.platform == "win32", reason="Symlinks require elevated privileges on Windows")
def test_symlinked_directory_out_of_the_project_is_not_followed(tmp_path):
    root = _project(tmp_path)
    secret = tmp_path / "secret"
    secret.mkdir()
    (secret / "test_s.py").write_text("def test_s():\n    pass\n")
    (root / "linked").symlink_to(secret, target_is_directory=True)
    assert ev.find_test_file(load_project(root), "linked.test_s::test_s") is None
    assert ev.find_test_file(load_project(root), "linked/test_s.py::test_s") is None


def test_ordinary_classnames_still_resolve(tmp_path):
    root = _project(tmp_path)
    (root / "tests").mkdir()
    (root / "tests" / "test_a.py").write_text("def test_a():\n    pass\n")
    proj = load_project(root)
    want = (root / "tests" / "test_a.py").resolve()
    assert ev.find_test_file(proj, "tests.test_a::test_a") == want
    assert ev.find_test_file(proj, "tests/test_a.py::test_a") == want
