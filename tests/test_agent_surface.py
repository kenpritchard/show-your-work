"""Agent-facing surface: tool schemas, handlers, slash command, report. Loaded as a package like Hermes does."""

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def pkg():
    spec = importlib.util.spec_from_file_location(
        "syw_plugin_under_test", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    import importlib as il

    return {
        "init": mod,
        "handlers": il.import_module("syw_plugin_under_test.handlers"),
        "schemas": il.import_module("syw_plugin_under_test.schemas"),
        "service": il.import_module("syw_plugin_under_test.show_your_work.service"),
        "report": il.import_module("syw_plugin_under_test.show_your_work.report"),
    }


@pytest.fixture
def proj(tmp_path, pkg):
    root = tmp_path / "app"
    root.mkdir()
    (root / "criteria.md").write_text("- [R1] first\n- [R2] second\n")
    (root / "syw.toml").write_text('criteria_file = "criteria.md"\ntracked = []\n')
    (root / "r.xml").write_bytes(
        b'<testsuite><testcase classname="t" name="a"/><testcase classname="t" name="b">'
        b'<failure message="boom"/></testcase></testsuite>'
    )
    h = pkg["handlers"]
    h._service = pkg["service"].Service(sqlite3.connect(tmp_path / "db.sqlite", check_same_thread=False))
    yield root
    h._service = None


class FakeCtx:
    def __init__(self):
        self.tools, self.commands, self.cli, self.skills = {}, {}, {}, {}

    def register_tool(self, name, toolset, schema, handler, check_fn=None, **kw):
        self.tools[name] = (schema, handler)

    def register_command(self, name, handler, description="", args_hint=""):
        self.commands[name] = handler

    def register_cli_command(self, name, help, setup_fn, handler_fn=None, description=""):
        self.cli[name] = (setup_fn, handler_fn)

    def register_skill(self, name, path, description=""):
        assert Path(path).is_file()
        self.skills[name] = path


def test_registers_exactly_the_declared_surface(pkg):
    ctx = FakeCtx()
    pkg["init"].register(ctx)
    assert set(ctx.tools) == {"syw_board", "syw_link", "syw_import", "syw_run_detail", "syw_test_evidence"}
    assert set(ctx.commands) == {"syw"} and set(ctx.cli) == {"syw"} and set(ctx.skills) == {"workflow"}
    manifest = (ROOT / "plugin.yaml").read_text()
    for name in ctx.tools:
        assert f"- {name}" in manifest


def test_no_agent_tool_can_record_a_review(pkg):
    schemas = pkg["schemas"].TOOL_SCHEMAS
    for name, schema in schemas.items():
        props = set(schema["parameters"]["properties"])
        assert not props & {"decision", "review", "accept", "accepted", "reviewer"}, name
        assert schema["parameters"]["additionalProperties"] is False


def test_service_refuses_non_human_reviewer(pkg, proj):
    svc = pkg["handlers"].service()
    with pytest.raises(ValueError, match="human"):
        svc.review(proj, "R1", "accepted", by="agent")


def test_tool_flow_link_import_board(pkg, proj):
    tool = pkg["handlers"].tool
    assert json.loads(tool("syw_link")({"project": str(proj), "requirement": "R1", "test_ids": ["t::a"]}))["ok"]
    imp = json.loads(tool("syw_import")({"project": str(proj), "report_path": "r.xml"}))
    assert imp["ok"] and imp["tests"] == 2
    board = json.loads(tool("syw_board")({"project": str(proj)}))
    rows = {r["id"]: r for r in board["requirements"]}
    assert rows["R1"]["outcome"] == "pass" and rows["R2"]["coverage"] == "none"
    detail = json.loads(tool("syw_run_detail")({"project": str(proj)}))
    assert detail["run"]["provenance"] == "agent-imported"


def test_tool_errors_are_json_not_exceptions(pkg, proj):
    tool = pkg["handlers"].tool
    out = json.loads(tool("syw_import")({"project": str(proj), "report_path": "../../etc/passwd"}))
    assert out["ok"] is False and "inside the project" in out["error"]
    out = json.loads(tool("syw_board")({"project": str(proj.parent / "nope")}))
    assert out["ok"] is False


def test_slash_accept_and_board(pkg, proj, monkeypatch):
    h = pkg["handlers"]
    monkeypatch.setattr(h, "_session_root", lambda: proj)
    assert "Recorded: R1 accepted" in h.slash("accept R1 checked by hand")
    text = h.slash("")
    assert "review: accepted" in text and "2 requirements" in text
    assert "Usage" in h.slash("accept")


def test_export_writes_markdown(pkg, proj, monkeypatch):
    h = pkg["handlers"]
    monkeypatch.setattr(h, "_session_root", lambda: proj)
    h.tool("syw_link")({"project": str(proj), "requirement": "R2", "test_ids": ["t::b"]})
    h.tool("syw_import")({"project": str(proj), "report_path": "r.xml"})
    out = Path(h.slash("export").removeprefix("Wrote ").strip())
    md = out.read_text()
    assert "| R2 |" in md and "boom" in md and "not proof" in md


def test_board_text_icons_and_passing_count(pkg):
    h = pkg["handlers"]
    def req(rid, outcome, fresh):
        return {"id": rid, "text": "t", "coverage": "linked", "tests": [1], "outcome": outcome,
                "freshness": fresh, "review": "none"}
    board = {"project": "/p", "latest_run": None,
             "summary": {"requirements": 4, "passing": 3, "untested": 0, "failing": 1, "stale": 1, "accepted": 0},
             "requirements": [req("R1", "pass", "current"), req("R2", "pass", "stale"),
                              req("R3", "pass", "unknown"), req("R4", "fail", "current")]}
    text = h.board_text(board)
    assert "3 passing" in text
    lines = {l.split()[1]: l.split()[0] for l in text.splitlines() if l[:1] in "✅⚠❔❌"}
    assert lines == {"R1": "✅", "R2": "⚠️", "R3": "❔", "R4": "❌"}


def test_export_flags_older_run_and_counts_passing(pkg):
    md = pkg["report"].render_markdown(
        {"project": "/p", "criteria_file": "c.md", "code": {"tracked_files": 1, "digest": "a" * 64},
         "latest_run": None, "summary": {"requirements": 1, "passing": 1, "untested": 0, "failing": 0,
                                         "stale": 0, "accepted": 0}, "requirements": []},
        [{"run_id": "r1", "imported_at": "t", "report_path": "x", "provenance": "agent-imported",
          "tests": 3, "older_report": True, "counts": {"pass": 2, "fail": 1}}])
    assert "1 passing" in md and "older than the code" in md
    assert "| 3 | 2 | 1 | 0 | 0 |" in md
