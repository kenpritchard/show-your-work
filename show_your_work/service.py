"""Application service shared by agent tools, slash command, CLI and the Desktop API.

The four columns per requirement are computed here and never merged:

    coverage   none | linked
    outcome    not run | pass | fail | error | skipped     (latest run, worst linked test wins)
    freshness  unknown | current | stale                    (tracked files vs. that run)
    review     none | accepted | rejected | stale           (human only; stale if wording or code changed)
"""

from __future__ import annotations

import hashlib
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import store
from .junit import parse_junit
from .project import Project, ProjectError, _inside, fingerprint, load_project, tracked_files

DECISIONS = ("accepted", "rejected")
PROVENANCE = ("agent-imported", "human-imported", "external")
# Higher rank = worse. "not run" counts as worse than skipped: a linked test that didn't run is a gap.
_RANK = {"pass": 0, "skipped": 1, "not run": 2, "error": 3, "fail": 4}
MAX_NOTE = 1000
MAX_REPORT_FILES = 500
MAX_FOLDER_BYTES = 50 * 1024 * 1024
# Marks a run whose report files are older than the newest tracked file: the plugin cannot tell
# which code it tested, so freshness is "unknown", never "current".
OLDER_REPORT = "older-report:"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Service:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = store.init(conn)
        self._lock = threading.Lock()

    # ---------- helpers ----------

    def _project(self, root) -> Project:
        return load_project(root)

    @staticmethod
    def _key(project: Project) -> str:
        return str(project.root)

    def _require(self, project: Project, requirement: str):
        for c in project.criteria:
            if c.id == requirement:
                return c
        raise KeyError(f"unknown requirement {requirement!r} in {project.criteria_file}")

    def _latest_run(self, key: str):
        return self.conn.execute(
            "SELECT * FROM runs WHERE project=? ORDER BY imported_at DESC, rowid DESC LIMIT 1", (key,)
        ).fetchone()

    # ---------- agent + human ----------

    def link(self, root, requirement: str, test_ids: list[str], by: str) -> dict:
        project = self._project(root)
        self._require(project, requirement)
        clean = [t.strip() for t in test_ids if t and t.strip()]
        if not clean:
            raise ValueError("no test ids given")
        with self._lock, self.conn:
            for t in clean:
                self.conn.execute(
                    "INSERT OR IGNORE INTO links VALUES (?,?,?,?,?)",
                    (self._key(project), requirement, t[:500], by, _now()),
                )
        return {"requirement": requirement, "linked": clean}

    def unlink(self, root, requirement: str, test_ids: list[str]) -> dict:
        project = self._project(root)
        with self._lock, self.conn:
            for t in test_ids:
                self.conn.execute(
                    "DELETE FROM links WHERE project=? AND requirement=? AND test_id=?",
                    (self._key(project), requirement, t),
                )
        return {"requirement": requirement, "unlinked": list(test_ids)}

    def import_report(self, root, report_path: str, provenance: str = "agent-imported") -> dict:
        if provenance not in PROVENANCE:
            raise ValueError(f"provenance must be one of {PROVENANCE}")
        project = self._project(root)
        path = _inside(project.root, report_path, "report path")
        if path.is_symlink() or not path.exists():
            raise ProjectError(f"report not found: {report_path}")
        if path.is_dir():
            # A folder of reports (Maven surefire/failsafe write one file per test class) = one run.
            files = sorted(p for p in path.glob("*.xml") if p.is_file() and not p.is_symlink())
            if not files:
                raise ProjectError(f"no .xml reports in folder: {report_path}")
            if len(files) > MAX_REPORT_FILES:
                raise ProjectError(f"more than {MAX_REPORT_FILES} report files in {report_path}")
            digest = hashlib.sha256()
            results, total = [], 0
            for f in files:
                data = f.read_bytes()
                total += len(data)
                if total > MAX_FOLDER_BYTES:
                    raise ValueError(f"reports in {report_path} exceed {MAX_FOLDER_BYTES // (1024 * 1024)} MB")
                try:
                    results.extend(parse_junit(data))
                except ValueError as exc:
                    raise ValueError(f"{f.name}: {exc}") from None
                digest.update(f.name.encode() + b"\0" + hashlib.sha256(data).digest())
            report_sha = digest.hexdigest()
            report_mtime = max(f.stat().st_mtime for f in files)
        else:
            data = path.read_bytes()
            results = parse_junit(data)
            report_sha = hashlib.sha256(data).hexdigest()
            report_mtime = path.stat().st_mtime
        fp = fingerprint(project)
        newest_code = max((p.stat().st_mtime for p in tracked_files(project)), default=0.0)
        warnings = []
        code_digest = fp.digest
        if newest_code > report_mtime:
            code_digest = OLDER_REPORT + fp.digest
            warnings.append("report is older than the newest tracked file, so it may not have tested the "
                            "current code; freshness will show 'unknown'. Rerun the tests and import again.")
        run_id = uuid.uuid4().hex[:12]
        with self._lock, self.conn:
            self.conn.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?)",
                (run_id, self._key(project), _now(), path.relative_to(project.root).as_posix(),
                 report_sha, provenance, code_digest, fp.file_count, len(results)),
            )
            self.conn.executemany(
                "INSERT INTO results VALUES (?,?,?,?,?)",
                [(run_id, i, r.test_id, r.outcome, r.message) for i, r in enumerate(results)],
            )
        counts: dict[str, int] = {}
        for r in results:
            counts[r.outcome] = counts.get(r.outcome, 0) + 1
        return {"run_id": run_id, "tests": len(results), "counts": counts, "warnings": warnings}

    # ---------- human only (never exposed as an agent tool) ----------

    def review(self, root, requirement: str, decision: str, note: str = "", by: str = "human") -> dict:
        if decision not in DECISIONS:
            raise ValueError(f"decision must be one of {DECISIONS}")
        if not by.startswith("human"):
            raise ValueError("reviews can only be recorded by a human surface")
        project = self._project(root)
        crit = self._require(project, requirement)
        fp = fingerprint(project)
        with self._lock, self.conn:
            self.conn.execute(
                "INSERT INTO reviews (project, requirement, decision, note, reviewer, reviewed_at,"
                " criterion_digest, code_digest) VALUES (?,?,?,?,?,?,?,?)",
                (self._key(project), requirement, decision, note[:MAX_NOTE], by, _now(),
                 crit.digest, fp.digest),
            )
        return {"requirement": requirement, "decision": decision}

    # ---------- read ----------

    def board(self, root) -> dict:
        project = self._project(root)
        key = self._key(project)
        fp = fingerprint(project)
        run = self._latest_run(key)
        results: dict[str, sqlite3.Row] = {}
        if run is not None:
            for r in self.conn.execute("SELECT * FROM results WHERE run_id=?", (run["run_id"],)):
                results[r["test_id"]] = r
        links: dict[str, list[str]] = {}
        for row in self.conn.execute(
            "SELECT requirement, test_id FROM links WHERE project=? ORDER BY test_id", (key,)
        ):
            links.setdefault(row["requirement"], []).append(row["test_id"])

        if run is None or run["code_digest"].startswith(OLDER_REPORT):
            freshness_run = "unknown"
        else:
            freshness_run = "current" if run["code_digest"] == fp.digest else "stale"

        reqs = []
        for c in project.criteria:
            tests = links.get(c.id, [])
            per_test = []
            for t in tests:
                r = results.get(t)
                per_test.append({"test_id": t, "outcome": r["outcome"] if r else "not run",
                                 "message": r["message"] if r else ""})
            if not tests or run is None:
                outcome = "not run"
            else:
                outcome = max((p["outcome"] for p in per_test), key=_RANK.__getitem__)
            rev = self.conn.execute(
                "SELECT * FROM reviews WHERE project=? AND requirement=? ORDER BY review_id DESC LIMIT 1",
                (key, c.id),
            ).fetchone()
            if rev is None:
                review = "none"
            elif rev["criterion_digest"] != c.digest or rev["code_digest"] != fp.digest:
                review = "stale"
            else:
                review = rev["decision"]
            reqs.append({
                "id": c.id,
                "text": c.text,
                "coverage": "linked" if tests else "none",
                "outcome": outcome,
                "freshness": freshness_run if tests else "unknown",
                "review": review,
                "review_detail": None if rev is None else {
                    "decision": rev["decision"], "note": rev["note"], "by": rev["reviewer"],
                    "at": rev["reviewed_at"]},
                "tests": per_test,
            })

        known = {c.id for c in project.criteria}
        orphans = [{"requirement": r, "test_id": t}
                   for r, ts in sorted(links.items()) if r not in known for t in ts]
        summary = {
            "requirements": len(reqs),
            "untested": sum(r["coverage"] == "none" for r in reqs),
            "passing": sum(r["outcome"] == "pass" for r in reqs),
            "failing": sum(r["outcome"] in ("fail", "error") for r in reqs),
            "stale": sum(r["freshness"] == "stale" for r in reqs),
            "accepted": sum(r["review"] == "accepted" for r in reqs),
        }
        return {
            "project": key,
            "criteria_file": project.criteria_file,
            "latest_run": None if run is None else dict(run),
            "code": {"digest": fp.digest, "tracked_files": fp.file_count},
            "summary": summary,
            "requirements": reqs,
            "orphan_links": orphans,
        }

    def runs(self, root, limit: int = 50) -> list[dict]:
        project = self._project(root)
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM runs WHERE project=? ORDER BY imported_at DESC, rowid DESC LIMIT ?",
            (self._key(project), limit),
        )]

    def run_detail(self, root, run_id: str) -> dict:
        project = self._project(root)
        run = self.conn.execute(
            "SELECT * FROM runs WHERE run_id=? AND project=?", (run_id, self._key(project))
        ).fetchone()
        if run is None:
            raise KeyError(f"no run {run_id!r} for this project")
        results = [dict(r) for r in self.conn.execute(
            "SELECT test_id, outcome, message FROM results WHERE run_id=? ORDER BY seq", (run_id,))]
        return {"run": dict(run), "results": results}


def default_service() -> Service:
    """Service backed by Hermes's per-profile plugin database."""
    from plugins.plugin_storage import plugin_db

    return Service(plugin_db("show-your-work"))


def resolve_root(root: str | None) -> Path:
    if not root:
        raise ProjectError("project path is required (folder containing syw.toml)")
    return Path(root).expanduser()
