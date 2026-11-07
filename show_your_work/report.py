"""Portable Markdown review report."""

from __future__ import annotations


def _cell(s: str) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def render_markdown(board: dict, runs: list[dict]) -> str:
    s = board["summary"]
    run = board["latest_run"]
    out = [
        "# Show Your Work: review report",
        "",
        f"- Project: `{board['project']}`",
        f"- Criteria file: `{board['criteria_file']}`",
        f"- Tracked files now: {board['code']['tracked_files']} (digest `{board['code']['digest'][:12]}`)",
        "- Latest run: " + ("none imported" if run is None else
                            f"`{run['run_id']}` at {run['imported_at']} from `{run['report_path']}` "
                            f"({run['provenance']}, report sha256 `{run['report_sha256'][:12]}`)"),
        "",
        f"**{s['requirements']} requirements: {s['untested']} untested, {s['failing']} failing, "
        f"{s['stale']} stale, {s['accepted']} accepted by a human.**",
        "",
        "| Req | Requirement | Coverage | Outcome | Freshness | Review |",
        "|---|---|---|---|---|---|",
    ]
    for r in board["requirements"]:
        cov = "**untested**" if r["coverage"] == "none" else ", ".join(f"`{t['test_id']}`" for t in r["tests"])
        out.append(f"| {r['id']} | {_cell(r['text'])} | {cov} | {r['outcome']} | {r['freshness']} | {r['review']} |")
    failures = [(r["id"], t) for r in board["requirements"] for t in r["tests"]
                if t["outcome"] in ("fail", "error")]
    if failures:
        out += ["", "## Failures", ""]
        out += [f"- **{rid}** `{t['test_id']}`: {_cell(t['message']) or '(no message)'}" for rid, t in failures]
    reviews = [r for r in board["requirements"] if r["review_detail"]]
    if reviews:
        out += ["", "## Human reviews", ""]
        for r in reviews:
            d = r["review_detail"]
            out.append(f"- **{r['id']}** {d['decision']} by {d['by']} at {d['at']}"
                       + (f": {_cell(d['note'])}" if d["note"] else "")
                       + (" *(stale: requirement wording or code changed since)*" if r["review"] == "stale" else ""))
    if runs:
        out += ["", "## Run history", "", "| Run | Imported | Report | Provenance | Tests |", "|---|---|---|---|---|"]
        out += [f"| `{x['run_id']}` | {x['imported_at']} | `{x['report_path']}` | {x['provenance']} | {x['tests']} |"
                for x in runs]
    out += ["", "---",
            "_A link between a test and a requirement is a coverage claim, not proof the test is adequate. "
            "Results are imported from reports; this plugin did not run the tests. Reviews are local records, "
            "not signatures._", ""]
    return "\n".join(out)
