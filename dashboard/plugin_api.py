"""HTTP namespace /api/plugins/show-your-work/ for the Desktop page.

The Desktop page is the human surface, so this is where review (sign-off) writes come from.
Hermes loads this file as a standalone module, so the plugin package is loaded by path.
"""

import hashlib
import importlib
import importlib.util
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

_ROOT = Path(__file__).resolve().parents[1]


def _own(module: str):
    name = "syw_api_pkg_" + hashlib.sha256(str(_ROOT).encode()).hexdigest()[:12]
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            name, _ROOT / "__init__.py", submodule_search_locations=[str(_ROOT)])
        if spec is None or spec.loader is None:
            raise ImportError("Show Your Work package cannot be loaded")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return importlib.import_module(f"{name}.{module}")


router = APIRouter()
MAX_BODY = 64 * 1024


def _service():
    return _own("handlers").service()


def _errors(fn):
    project_error = _own("show_your_work.project").ProjectError
    try:
        return fn()
    except KeyError as exc:
        raise HTTPException(404, str(exc).strip("'\"")) from None
    except (project_error, ValueError) as exc:
        raise HTTPException(400, str(exc)) from None
    except OSError as exc:
        raise HTTPException(503, f"storage or file error: {exc}") from None


def _check_origin(request: Request):
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "cross-site requests are not accepted")


async def _json(request: Request, required: set, optional: set | frozenset = frozenset()) -> dict:
    _check_origin(request)
    body = await request.body()
    if len(body) > MAX_BODY:
        raise HTTPException(413, "request too large")
    try:
        import json

        value = json.loads(body or b"{}")
    except ValueError:
        raise HTTPException(400, "invalid JSON") from None
    if not isinstance(value, dict) or required - set(value) or set(value) - required - set(optional):
        raise HTTPException(400, f"expected fields {sorted(required)} (+ optional {sorted(optional)})")
    return value


def _str(value, maximum=1024) -> str:
    if not isinstance(value, str) or not 0 < len(value) <= maximum:
        raise HTTPException(400, "invalid field")
    return value


@router.get("/ping")
async def ping():
    return {"ok": True, "plugin": "show-your-work"}


@router.get("/projects")
async def projects():
    """Projects this profile has seen (any link, run or review), most recent first."""
    svc = _service()
    rows = svc.conn.execute(
        "SELECT project, MAX(t) AS last FROM ("
        " SELECT project, imported_at AS t FROM runs UNION ALL"
        " SELECT project, linked_at FROM links UNION ALL"
        " SELECT project, reviewed_at FROM reviews) GROUP BY project ORDER BY last DESC LIMIT 50"
    ).fetchall()
    return {"projects": [{"path": r["project"], "last_activity": r["last"],
                          "exists": (Path(r["project"]) / "syw.toml").is_file()} for r in rows]}


@router.get("/board")
async def board(project: str):
    return _errors(lambda: _service().board(Path(_str(project))))


@router.get("/runs")
async def runs(project: str):
    return _errors(lambda: {"runs": _service().runs(Path(_str(project)))})


@router.get("/run")
async def run(project: str, run_id: str):
    return _errors(lambda: _service().run_detail(Path(_str(project)), _str(run_id, 32)))


@router.post("/review")
async def review(request: Request):
    v = await _json(request, {"project", "requirement", "decision"}, {"note"})
    note = v.get("note", "")
    if not isinstance(note, str):
        raise HTTPException(400, "note must be a string")
    return _errors(lambda: _service().review(
        Path(_str(v["project"])), _str(v["requirement"], 32), _str(v["decision"], 16),
        note=note, by="human:desktop"))


@router.post("/import")
async def import_report(request: Request):
    v = await _json(request, {"project", "report_path"})
    return _errors(lambda: _service().import_report(
        Path(_str(v["project"])), _str(v["report_path"]), provenance="human-imported"))


@router.post("/export")
async def export(request: Request):
    v = await _json(request, {"project"})
    return _errors(lambda: {"path": str(_own("handlers").write_export(Path(_str(v["project"]))))})
