"""Tool, slash-command and CLI handlers. Thin wrappers over show_your_work.service."""

from __future__ import annotations

import json
import shlex
from pathlib import Path

from .show_your_work.project import ProjectError
from .show_your_work.report import render_markdown
from .show_your_work.service import Service, default_service, resolve_root

_service: Service | None = None


def service() -> Service:
    global _service
    if _service is None:
        _service = default_service()
    return _service


def _ok(payload) -> str:
    return json.dumps({"ok": True, **payload} if isinstance(payload, dict) else {"ok": True, "data": payload})


def _err(exc: Exception) -> str:
    return json.dumps({"ok": False, "error": str(exc).strip("'\"")})


# ---------- agent tools ----------

def tool(name: str):
    def handle(args: dict, **kwargs) -> str:
        try:
            svc = service()
            root = resolve_root(args.get("project"))
            if name == "syw_board":
                return _ok(svc.board(root))
            if name == "syw_link":
                return _ok(svc.link(root, args["requirement"], args["test_ids"], by="agent"))
            if name == "syw_import":
                return _ok(svc.import_report(root, args["report_path"], provenance="agent-imported"))
            if name == "syw_run_detail":
                run_id = args.get("run_id")
                if not run_id:
                    latest = svc.runs(root, limit=1)
                    if not latest:
                        raise KeyError("no runs imported yet")
                    run_id = latest[0]["run_id"]
                return _ok(svc.run_detail(root, run_id))
            raise ValueError(f"unknown tool {name}")
        except (ProjectError, ValueError, KeyError, OSError) as exc:
            return _err(exc)

    return handle


# ---------- /syw slash command (human-typed) ----------

SLASH_HELP = """Show Your Work
  /syw                         board for the session's working folder
  /syw board [path]            board for a project folder
  /syw accept <R#> [note]      record YOUR sign-off on a requirement
  /syw reject <R#> [note]      record that a requirement is not acceptable
  /syw export [path]           write show-your-work-review.md into the project"""

_ICON = {"pass": "✅", "fail": "❌", "error": "❌", "skipped": "⏭", "not run": "·"}


def _icon(r: dict) -> str:
    # A pass on code the plugin can't vouch for must not look like a plain green check.
    if r["outcome"] == "pass" and r["freshness"] == "stale":
        return "⚠️"
    if r["outcome"] == "pass" and r["freshness"] == "unknown":
        return "❔"
    return _ICON.get(r["outcome"], "?")


def summary_line(s: dict) -> str:
    return (f"{s['requirements']} requirements · {s['passing']} passing · {s['untested']} untested · "
            f"{s['failing']} failing · {s['stale']} stale · {s['accepted']} accepted")


def _session_root() -> Path:
    try:
        from agent.runtime_cwd import resolve_agent_cwd

        return resolve_agent_cwd()
    except Exception:
        return Path.cwd()


def _find_project(start: Path) -> Path:
    for p in (start, *start.parents):
        if (p / "syw.toml").is_file():
            return p
    raise ProjectError(f"no syw.toml in {start} or any parent folder")


def board_text(board: dict) -> str:
    s = board["summary"]
    lines = [
        f"Show Your Work: {board['project']}",
        summary_line(s),
    ]
    if board.get("latest_run") and board["latest_run"].get("older_report"):
        lines.append("warning: the latest run's report was older than the code when imported; freshness is unknown")
    for r in board["requirements"]:
        cov = "untested" if r["coverage"] == "none" else f"{len(r['tests'])} test(s)"
        lines.append(
            f"{_icon(r)} {r['id']}  {r['text'][:60]}  [{cov} | {r['outcome']} | "
            f"{r['freshness']} | review: {r['review']}]"
        )
    lines.append("Icons: ✅ pass on current code · ⚠️ pass, code changed since · ❔ pass, unverified code · "
                 "❌ fail/error · ⏭ skipped · · not run")
    return "\n".join(lines)


def slash(raw_args: str) -> str:
    try:
        parts = shlex.split(raw_args or "")
    except ValueError as exc:
        return f"Could not parse arguments: {exc}"
    cmd = parts[0].lower() if parts else "board"
    try:
        if cmd in ("help", "-h", "--help"):
            return SLASH_HELP
        if cmd == "board":
            root = Path(parts[1]).expanduser() if len(parts) > 1 else _find_project(_session_root())
            return board_text(service().board(root))
        if cmd in ("accept", "reject"):
            if len(parts) < 2:
                return f"Usage: /syw {cmd} <R#> [note]"
            root = _find_project(_session_root())
            decision = "accepted" if cmd == "accept" else "rejected"
            service().review(root, parts[1], decision, note=" ".join(parts[2:]), by="human:slash")
            return f"Recorded: {parts[1]} {decision} by you."
        if cmd == "export":
            root = Path(parts[1]).expanduser() if len(parts) > 1 else _find_project(_session_root())
            out = write_export(root)
            return f"Wrote {out}"
        return SLASH_HELP
    except (ProjectError, ValueError, KeyError, OSError) as exc:
        return f"Show Your Work: {str(exc).strip(chr(39))}"


def write_export(root: Path) -> Path:
    svc = service()
    board = svc.board(root)
    md = render_markdown(board, svc.runs(root, limit=10))
    out = Path(board["project"]) / "show-your-work-review.md"
    out.write_text(md, encoding="utf-8")
    return out


# ---------- hermes syw (terminal CLI) ----------

def cli_setup(parser):
    sub = parser.add_subparsers(dest="syw_cmd")
    for name, help_ in (("board", "Print the board"), ("export", "Write the Markdown review report")):
        p = sub.add_parser(name, help=help_)
        p.add_argument("project", nargs="?", default=".")
    p = sub.add_parser("import", help="Import a JUnit XML report you ran yourself")
    p.add_argument("report")
    p.add_argument("--project", default=".")
    for name in ("accept", "reject"):
        p = sub.add_parser(name, help=f"Record your review: {name}")
        p.add_argument("requirement")
        p.add_argument("note", nargs="*")
        p.add_argument("--project", default=".")


def cli_run(args):
    cmd = getattr(args, "syw_cmd", None) or "board"
    try:
        if cmd == "board":
            print(board_text(service().board(_find_project(Path(args.project).resolve()))))
        elif cmd == "export":
            print(f"Wrote {write_export(_find_project(Path(args.project).resolve()))}")
        elif cmd == "import":
            root = _find_project(Path(args.project).resolve())
            rel = Path(args.report).resolve().relative_to(root).as_posix() \
                if Path(args.report).is_absolute() else args.report
            out = service().import_report(root, rel, provenance="human-imported")
            print(f"Imported run {out['run_id']}: {out['tests']} tests {out['counts']}")
            for w in out.get("warnings", []):
                print(f"warning: {w}")
        elif cmd in ("accept", "reject"):
            root = _find_project(Path(args.project).resolve())
            decision = "accepted" if cmd == "accept" else "rejected"
            service().review(root, args.requirement, decision, note=" ".join(args.note), by="human:cli")
            print(f"Recorded: {args.requirement} {decision}")
        return 0
    except (ProjectError, ValueError, KeyError, OSError) as exc:
        print(f"show-your-work: {str(exc).strip(chr(39))}")
        return 1
