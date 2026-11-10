"""Desktop HTTP API, through FastAPI's TestClient with a temp database and project."""

import importlib.util
import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
P = "/api/plugins/show-your-work"


@pytest.fixture
def api(tmp_path):
    spec = importlib.util.spec_from_file_location("syw_api_test", ROOT / "dashboard" / "plugin_api.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    handlers = mod._own("handlers")
    service_mod = mod._own("show_your_work.service")
    handlers._service = service_mod.Service(sqlite3.connect(tmp_path / "db.sqlite", check_same_thread=False))
    app = FastAPI()
    app.include_router(mod.router, prefix=P)
    yield TestClient(app)
    handlers._service = None


@pytest.fixture
def proj(tmp_path):
    root = tmp_path / "app"
    root.mkdir()
    (root / "criteria.md").write_text("- [R1] first\n- [R2] second\n")
    (root / "syw.toml").write_text('criteria_file = "criteria.md"\ntracked = []\n')
    (root / "r.xml").write_bytes(b'<testsuite><testcase classname="t" name="a"/></testsuite>')
    return root


def test_board_and_review_round_trip(api, proj):
    b = api.get(f"{P}/board", params={"project": str(proj)}).json()
    assert b["summary"]["untested"] == 2
    r = api.post(f"{P}/review", json={"project": str(proj), "requirement": "R1",
                                      "decision": "accepted", "note": "ok"})
    assert r.status_code == 200
    b = api.get(f"{P}/board", params={"project": str(proj)}).json()
    row = b["requirements"][0]
    assert row["review"] == "accepted" and row["review_detail"]["by"] == "human:desktop"


def test_projects_list_after_activity(api, proj):
    api.post(f"{P}/import", json={"project": str(proj), "report_path": "r.xml"})
    listed = api.get(f"{P}/projects").json()["projects"]
    assert listed[0]["path"] == str(proj.resolve()) and listed[0]["exists"]


def test_import_and_run_detail(api, proj):
    out = api.post(f"{P}/import", json={"project": str(proj), "report_path": "r.xml"}).json()
    detail = api.get(f"{P}/run", params={"project": str(proj), "run_id": out["run_id"]}).json()
    assert detail["run"]["provenance"] == "human-imported"
    assert detail["results"][0]["test_id"] == "t::a"


def test_bad_inputs_are_4xx_not_500(api, proj):
    assert api.post(f"{P}/review", json={"project": str(proj), "requirement": "R9",
                                         "decision": "accepted"}).status_code == 404
    assert api.post(f"{P}/review", json={"project": str(proj), "requirement": "R1",
                                         "decision": "vibes"}).status_code == 400
    assert api.post(f"{P}/review", json={"project": str(proj)}).status_code == 400
    assert api.post(f"{P}/review", json={"project": str(proj), "requirement": "R1",
                                         "decision": "accepted", "extra": 1}).status_code == 400
    assert api.post(f"{P}/import", json={"project": str(proj),
                                         "report_path": "../x.xml"}).status_code == 400
    assert api.get(f"{P}/board", params={"project": str(proj.parent / "nope")}).status_code == 400


def test_cross_site_post_refused(api, proj):
    r = api.post(f"{P}/review", headers={"sec-fetch-site": "cross-site"},
                 json={"project": str(proj), "requirement": "R1", "decision": "accepted"})
    assert r.status_code == 403


def test_evidence_and_change_endpoints(api, tmp_path):
    import shutil
    import subprocess
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    root = tmp_path / "g"
    (root / "tests").mkdir(parents=True)
    (root / "app.py").write_text("x = 1\n")
    (root / "tests" / "test_a.py").write_text("def test_a():\n    assert 1\n")
    (root / "criteria.md").write_text("- [R1] a\n")
    (root / "syw.toml").write_text('criteria_file = "criteria.md"\ntracked = ["*.py"]\nbase = "main"\n')
    run = lambda *a: subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                                    check=True, capture_output=True)
    run("init", "-q", "-b", "main"); run("add", "-A"); run("commit", "-qm", "b"); run("checkout", "-qb", "f")
    (root / "app.py").write_text("x = 2\n")
    (root / "tests" / "test_a.py").write_text("def test_a():\n    assert 1\n\n\ndef test_b():\n    assert 2\n")
    ev = api.get(f"{P}/evidence", params={"project": str(root), "test_id": "tests.test_a::test_b"}).json()
    assert ev["status"] == "new test" and ev["file"] == "tests/test_a.py" and "+def test_b" in ev["diff"]
    ch = api.get(f"{P}/change", params={"project": str(root)}).json()
    assert ch["production_files"] == ["app.py"] and "+x = 2" in ch["diff"]
    bad = api.get(f"{P}/evidence", params={"project": str(root), "test_id": ""})
    assert bad.status_code in (400, 422)
