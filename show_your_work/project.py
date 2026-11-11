"""A Show Your Work project: a folder with a syw.toml, a criteria file and tracked files.

syw.toml:

    criteria_file = "criteria.md"
    tracked = ["src/**/*.py", "tests/**/*.py"]   # changes here make results stale
    base = "origin/main"                         # optional: what the review diff compares against
"""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .criteria import Criterion, parse_criteria

CONFIG_NAME = "syw.toml"
MAX_TRACKED_FILES = 5000
MAX_CRITERIA_BYTES = 5 * 1024 * 1024  # same cap as a JUnit report


class ProjectError(ValueError):
    pass


@dataclass(frozen=True)
class Project:
    root: Path
    criteria_file: str
    tracked: list[str]
    criteria: list[Criterion]
    base: str = ""


@dataclass(frozen=True)
class Fingerprint:
    digest: str
    file_count: int


def _inside(root: Path, rel: str, what: str) -> Path:
    p = PurePosixPath(rel)
    if p.is_absolute() or ".." in p.parts:
        raise ProjectError(f"{what} must stay inside the project: {rel!r}")
    full = (root / rel).resolve()
    if not full.is_relative_to(root):
        raise ProjectError(f"{what} must stay inside the project: {rel!r}")
    return full


def load_project(root: str | Path) -> Project:
    root = Path(root).resolve()
    cfg_path = root / CONFIG_NAME
    if not cfg_path.is_file():
        raise ProjectError(f"no {CONFIG_NAME} in {root}")
    try:
        cfg = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ProjectError(f"{CONFIG_NAME} is not valid TOML: {exc}") from None
    criteria_file = cfg.get("criteria_file", "criteria.md")
    tracked = cfg.get("tracked", [])
    base = cfg.get("base", "")
    if not isinstance(base, str):
        raise ProjectError(f"{CONFIG_NAME}: base must be a string (a git ref such as \"origin/main\")")
    if not isinstance(criteria_file, str) or not isinstance(tracked, list) or not all(
        isinstance(t, str) for t in tracked
    ):
        raise ProjectError(f"{CONFIG_NAME}: criteria_file must be a string, tracked a list of strings")
    crit_path = _inside(root, criteria_file, "criteria_file")
    for pattern in tracked:
        _inside(root, pattern.split("*", 1)[0] or ".", "tracked pattern")
    if not crit_path.is_file():
        raise ProjectError(f"criteria file not found: {criteria_file}")
    if crit_path.stat().st_size > MAX_CRITERIA_BYTES:
        raise ProjectError(
            f"{criteria_file}: criteria file too large (limit {MAX_CRITERIA_BYTES // (1024 * 1024)} MB)"
        )
    try:
        criteria = parse_criteria(crit_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ProjectError(f"{criteria_file}: {exc}") from None
    return Project(root, criteria_file, list(tracked), criteria, base.strip())


def tracked_files(project: Project) -> list[Path]:
    files: set[Path] = set()
    for pattern in project.tracked:
        for p in project.root.glob(pattern):
            if p.is_symlink() or not p.is_file():
                continue
            rp = p.resolve()
            if rp.is_relative_to(project.root):
                files.add(rp)
            if len(files) > MAX_TRACKED_FILES:
                raise ProjectError(f"more than {MAX_TRACKED_FILES} tracked files; narrow the patterns")
    return sorted(files)


def fingerprint(project: Project) -> Fingerprint:
    """One hash over the relative path and contents of every tracked file."""
    h = hashlib.sha256()
    files = tracked_files(project)
    for f in files:
        h.update(f.relative_to(project.root).as_posix().encode() + b"\0")
        h.update(hashlib.sha256(f.read_bytes()).digest())
    return Fingerprint(h.hexdigest(), len(files))
