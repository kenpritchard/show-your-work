"""Parse acceptance criteria from a Markdown file.

A requirement is a list item that starts with a bracketed id:

    - [R1] Tip is 15% by default

Everything else in the file is ignored, so criteria can live inside normal prose.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

_LINE = re.compile(r"^\s*[-*]\s+\[([A-Za-z][A-Za-z0-9_.-]{0,31})\]\s+(.+?)\s*$")


@dataclass(frozen=True)
class Criterion:
    id: str
    text: str
    digest: str  # changes when the wording changes; whitespace-insensitive


def _digest(text: str) -> str:
    normalized = " ".join(text.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def parse_criteria(text: str) -> list[Criterion]:
    found: list[Criterion] = []
    seen: set[str] = set()
    for line in text.splitlines():
        m = _LINE.match(line)
        if not m:
            continue
        cid, body = m.group(1), " ".join(m.group(2).split())
        if cid in seen:
            raise ValueError(f"duplicate requirement id {cid}")
        seen.add(cid)
        found.append(Criterion(cid, body, _digest(body)))
    if not found:
        raise ValueError("no requirements found (expected lines like '- [R1] text')")
    return found
