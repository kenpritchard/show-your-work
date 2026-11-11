"""Review evidence for one linked test: where its source is, what the method looks like, and the git diff.

This is the only part of the plugin that starts a subprocess. It runs read-only ``git`` commands
(``rev-parse``, ``merge-base``, ``diff``) inside the project folder, only when a human opens a test on
the Desktop page or the agent asks for it, with a timeout, no shell, and a scrubbed environment.

Locating a test is a best guess from its JUnit id (``classname::name``):

- Java/Kotlin/Scala/Groovy: ``io.netty.FooTest`` -> ``**/io/netty/FooTest.<ext>`` (nested ``Outer$Inner`` -> Outer).
- Python: ``tests.test_tip`` -> ``tests/test_tip.py``, also ``tests/test_tip.py`` style classnames.
- Anything else: a file whose stem is the last part of the classname.

The method is found by name (``void name(``, ``def name(``, ``fun name(``, ``it("name"``, ``test("name"``)
and its body by brace depth (C-like) or indentation (Python). When that fails, the whole file is shown.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path, PurePosixPath, PureWindowsPath

from .project import Project

MAX_SOURCE_CHARS = 20_000
MAX_DIFF_CHARS = 60_000
GIT_TIMEOUT_S = 10
_JVM_EXTS = (".java", ".kt", ".scala", ".groovy")
_SKIP_DIRS = {".git", "node_modules", "target", "build", ".venv", "venv", "__pycache__", "dist", "out"}
_SUFFIX = re.compile(r"(\(.*\))?(\[[^\]]*\])*$")  # JUnit "(Type)[3]" / pytest "[param]"


class EvidenceError(ValueError):
    pass


# ---------------------------------------------------------------- git

def _git(root: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL", "SYSTEMROOT")}
    env.update(GIT_PAGER="cat", GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "--no-pager", *args],
            capture_output=True, text=True, timeout=GIT_TIMEOUT_S, env=env, check=False,
            encoding="utf-8", errors="replace",
        )
    except FileNotFoundError:
        raise EvidenceError("git is not installed, so no diff can be shown") from None
    except subprocess.TimeoutExpired:
        raise EvidenceError(f"git took longer than {GIT_TIMEOUT_S}s") from None
    if out.returncode != 0:
        raise EvidenceError((out.stderr or out.stdout).strip().splitlines()[-1] if (out.stderr or out.stdout)
                            else f"git {args[0]} failed")
    return out.stdout


_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@{}~^-]{0,200}$")


def resolve_base(project: Project) -> dict:
    """The commit the review diff starts from: merge-base of HEAD and ``base`` (or the upstream)."""
    root = project.root
    try:
        _git(root, "rev-parse", "--is-inside-work-tree")
    except EvidenceError:
        return {"ok": False, "reason": "not a git repository, so there is no diff to show"}
    wanted = project.base or ""
    source = "syw.toml base"
    if not wanted:
        try:
            wanted = _git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}").strip()
            source = "branch upstream"
        except EvidenceError:
            return {"ok": False, "reason": "no base set: add base = \"origin/main\" (or similar) to syw.toml"}
    if not _REF.match(wanted) or wanted.startswith("-"):
        return {"ok": False, "reason": f"base {wanted!r} is not a valid git ref"}
    try:
        commit = _git(root, "merge-base", "HEAD", wanted).strip()
    except EvidenceError as exc:
        return {"ok": False, "reason": f"base {wanted!r}: {exc}"}
    return {"ok": True, "ref": wanted, "commit": commit, "source": source}


def _diff(root: Path, base: str, paths: list[str] | None = None) -> str:
    args = ["diff", "--no-color", "--no-ext-diff", "-U3", base]
    if paths:
        args += ["--", *paths]
    return _git(root, *args)


def changed_files(project: Project, base: str) -> list[dict]:
    out = _git(project.root, "diff", "--no-color", "--numstat", base)
    files = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            add, rem, path = parts
            files.append({"path": path, "added": int(add) if add.isdigit() else 0,
                          "removed": int(rem) if rem.isdigit() else 0})
    untracked = _git(project.root, "ls-files", "--others", "--exclude-standard")
    for path in untracked.splitlines():
        files.append({"path": path, "added": None, "removed": 0, "untracked": True})
    return files


# ---------------------------------------------------------------- locating a test

def split_test_id(test_id: str) -> tuple[str, str]:
    cls, sep, name = test_id.partition("::")
    if not sep:
        cls, name = "", test_id
    name = _SUFFIX.sub("", name.strip()) or name.strip()
    return cls.strip(), name


def _walk(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        for f in filenames:
            yield Path(dirpath) / f


def _unsafe_classname(cls: str) -> bool:
    """A classname that names a path outside the project (absolute, a drive, or ``..``).

    JUnit ids come from a report the agent or a repo supplies, so they are untrusted. Refusing these
    before any filesystem probe keeps the "not found" answer from revealing whether a file exists
    outside the project.
    """
    posix = cls.replace("\\", "/")
    return (posix.startswith("/") or bool(PureWindowsPath(cls).drive)
            or ".." in PurePosixPath(posix).parts)


def _project_file(root: Path, cand: Path) -> Path | None:
    """``cand`` resolved, if it is a file inside the project; never probes outside it."""
    resolved = cand.resolve()
    if not resolved.is_relative_to(root):
        return None
    return resolved if resolved.is_file() else None


def find_test_file(project: Project, test_id: str) -> Path | None:
    cls, _ = split_test_id(test_id)
    if not cls or _unsafe_classname(cls):
        return None
    root = project.root
    # pytest classnames are sometimes a path already: "tests/test_tip.py" or "tests.test_tip.TestX"
    if cls.endswith(".py") and (hit := _project_file(root, root / cls)):
        return hit
    parts = cls.split(".")
    if any(PurePosixPath(p.replace("\\", "/")).is_absolute() for p in parts if p):
        return None  # "a./etc/x" would join to an absolute path
    for i in range(len(parts), 0, -1):  # tests.test_tip.TestClass -> try tests/test_tip.py first by length
        cand = root.joinpath(*parts[:i]).with_suffix(".py")
        if hit := _project_file(root, cand):
            return hit
    outer = parts[-1].split("$", 1)[0]
    pkg_path = "/".join(parts[:-1] + [outer])
    stem_hits = []
    for p in _walk(root):
        if p.is_symlink():
            continue
        posix = p.relative_to(root).as_posix()
        if p.suffix in _JVM_EXTS and posix.endswith(pkg_path + p.suffix):
            return p.resolve()
        if p.stem == outer and p.suffix in _JVM_EXTS + (".py", ".ts", ".js", ".go", ".cs", ".rb"):
            stem_hits.append(p)
    if len(stem_hits) == 1:
        return stem_hits[0].resolve()
    return None


_DECL = [
    # Java/Kotlin/Scala/Groovy/C#: "void name(", "fun name(", "def name(" ... the name followed by "("
    lambda n: re.compile(rf"^\s*(?:@\w+[^\n]*\n\s*)*[\w<>\[\],\s@.]*\b(?:void|fun|def|Task|async\s+Task)?\s*{re.escape(n)}\s*\("),
    lambda n: re.compile(rf"^\s*(?:async\s+)?def\s+{re.escape(n)}\s*\("),                  # Python
    lambda n: re.compile(rf"""^\s*(?:it|test|describe)\s*\(\s*['"`]{re.escape(n)}['"`]"""),  # JS
    lambda n: re.compile(rf"^\s*func\s+{re.escape(n)}\s*\("),                               # Go
]


def find_method(text: str, name: str, python: bool) -> tuple[int, int] | None:
    """Return 1-based (start, end) line numbers of the test method, or None."""
    lines = text.splitlines()
    pats = [p(name) for p in _DECL]
    start = None
    for i, line in enumerate(lines):
        if any(p.match(line) for p in pats) and not line.lstrip().startswith(("//", "*", "#")):
            start = i
            break
    if start is None:
        return None
    # include annotations / decorators directly above
    top = start
    while top > 0 and lines[top - 1].lstrip().startswith(("@",)):
        top -= 1
    if python:
        indent = len(lines[start]) - len(lines[start].lstrip())
        end = start
        for j in range(start + 1, len(lines)):
            s = lines[j]
            if s.strip() and (len(s) - len(s.lstrip())) <= indent:
                break
            end = j
        while end > start and not lines[end].strip():
            end -= 1
        return top + 1, end + 1
    depth, seen = 0, False
    for j in range(start, len(lines)):
        code = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//.*$', "", lines[j])
        for ch in code:
            if ch == "{":
                depth += 1
                seen = True
            elif ch == "}":
                depth -= 1
        if seen and depth <= 0:
            return top + 1, j + 1
    return None


# ---------------------------------------------------------------- diff slicing

_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def hunks_overlapping(diff: str, start: int, end: int) -> str:
    """Keep the file header plus the hunks whose new-side range overlaps [start, end]."""
    out, header, hunk, keep = [], [], [], False
    for line in diff.splitlines():
        m = _HUNK.match(line)
        if m:
            if hunk and keep:
                out += hunk
            new_start = int(m.group(3))
            new_len = int(m.group(4) or "1")
            keep = new_start <= end and (new_start + max(new_len, 1) - 1) >= start
            hunk = [line]
        elif hunk:
            hunk.append(line)
        else:
            header.append(line)
    if hunk and keep:
        out += hunk
    return "\n".join(header + out) if out else ""


def trim_to_range(diff: str, start: int, end: int) -> str:
    """Cut a file diff down to the lines inside [start, end] (new-side numbers), with 2 lines of context.

    Returns "" when nothing inside the range was added or removed (context-only overlap)."""
    header, body, changed = [], [], False
    new_no = 0
    in_hunk = False
    lo, hi = start - 2, end + 2
    for line in diff.splitlines():
        m = _HUNK.match(line)
        if m:
            new_no = int(m.group(3))
            in_hunk = True
            continue
        if not in_hunk:
            header.append(line)
            continue
        tag = line[:1]
        if tag == "+":
            if start <= new_no <= end:
                body.append((new_no, line))
                changed = True
            new_no += 1
        elif tag == "-":
            if start <= new_no <= end + 1:
                body.append((new_no, line))
                changed = True
        elif tag == "\\":
            continue
        else:
            if lo <= new_no <= hi:
                body.append((new_no, line))
            new_no += 1
    if not changed:
        return ""
    first = body[0][0]
    adds = sum(1 for _, l in body if l.startswith("+"))
    ctx = sum(1 for _, l in body if l.startswith(" "))
    rems = sum(1 for _, l in body if l.startswith("-"))
    hunk = f"@@ -{first} +{first},{adds + ctx} @@ (lines {start}-{end}; {adds} added, {rems} removed)"
    return "\n".join(header + [hunk] + [l for _, l in body])


def _cap(s: str, limit: int) -> tuple[str, bool]:
    return (s, False) if len(s) <= limit else (s[:limit] + "\n… (truncated)", True)


# ---------------------------------------------------------------- the one entry point

def test_evidence(project: Project, test_id: str) -> dict:
    cls, name = split_test_id(test_id)
    path = find_test_file(project, test_id)
    result: dict = {"test_id": test_id, "class": cls, "method": name, "file": None, "lines": None,
                    "source": None, "method_found": False, "diff": None, "diff_scope": None,
                    "status": None, "base": None, "notes": []}
    if path is None:
        result["notes"].append("could not find this test's source file from its id")
    else:
        rel = path.relative_to(project.root).as_posix()
        result["file"] = rel
        text = path.read_text(encoding="utf-8", errors="replace")
        span = find_method(text, name, python=path.suffix == ".py")
        if span:
            a, b = span
            result.update(lines=[a, b], method_found=True)
            src = "\n".join(text.splitlines()[a - 1:b])
        else:
            result["notes"].append(f"could not find method {name!r} in {rel}; showing the whole file")
            src = text
        result["source"], cut = _cap(src, MAX_SOURCE_CHARS)
        if cut:
            result["notes"].append("source truncated")
    base = resolve_base(project)
    result["base"] = base
    if not base["ok"]:
        result["notes"].append(base["reason"])
        return result
    if result["file"]:
        try:
            full = _diff(project.root, base["commit"], [result["file"]])
        except EvidenceError as exc:
            result["notes"].append(f"diff unavailable: {exc}")
            return result
        try:
            base_text = _git(project.root, "show", f"{base['commit']}:{result['file']}")
        except EvidenceError:
            base_text = None
        if not full.strip():
            if base_text is None:
                result["status"] = "new file, not committed or staged"
                result["notes"].append("git can't diff a file it doesn't know about yet; commit or `git add` it")
            else:
                result["status"] = "unchanged"
            return result
        if base_text is None:
            result["status"] = "new test (new file)"
        elif find_method(base_text, name, python=path.suffix == ".py") is None:
            result["status"] = "new test"
        else:
            result["status"] = "changed test"
        result["file_changed"] = True
        if result["method_found"]:
            a, b = result["lines"]
            sliced = trim_to_range(full, a, b)
            if not sliced:
                result["status"] = "unchanged test (other parts of the file changed)"
                return result
            result["diff"], _ = _cap(sliced, MAX_DIFF_CHARS)
            result["diff_scope"] = "method"
        else:
            result["diff"], _ = _cap(full, MAX_DIFF_CHARS)
            result["diff_scope"] = "file"
    return result


def change_evidence(project: Project, exclude_tests: bool = True) -> dict:
    """The whole change under review: changed files and the diff of the non-test files."""
    base = resolve_base(project)
    if not base["ok"]:
        return {"base": base, "files": [], "diff": None, "notes": [base["reason"]]}
    own = {"syw.toml", project.criteria_file, "show-your-work-review.md"}
    files = [f for f in changed_files(project, base["commit"]) if f["path"] not in own]
    def is_test(p: str) -> bool:
        q = p.lower()
        return "/test/" in q or "/tests/" in q or q.startswith(("test/", "tests/")) or \
            Path(q).stem.startswith("test_") or Path(q).stem.endswith(("test", "tests", "_test", "spec", "it"))
    prod = [f["path"] for f in files if not f.get("untracked") and not (exclude_tests and is_test(f["path"]))]
    diff = _diff(project.root, base["commit"], prod) if prod else ""
    diff, cut = _cap(diff, MAX_DIFF_CHARS)
    notes = ["diff truncated"] if cut else []
    if any(f.get("untracked") for f in files):
        notes.append("some new files aren't committed or staged, so git can't diff them")
    return {"base": base, "files": files, "diff": diff, "production_files": prod, "notes": notes}
