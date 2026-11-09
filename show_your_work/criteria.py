"""Parse acceptance criteria from a Markdown file.

A requirement is a list item that starts with a bracketed id containing a digit:

    - [R1] Tip is 15% by default
    1. [BUG42-1] split(100, 3) gives 33.33 each      (numbered lists work too)
    - [ ] [AC2] Refund over the total is rejected     (GitHub task-list style)

Everything else is ignored, so criteria can live inside a ticket, bug report or spec. The digit
rule keeps ordinary checkboxes (``- [x] done``) and labels (``- [Note] ...``) from being read as
requirements.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

_LINE = re.compile(
    r"^\s*(?:[-*+]|\d+[.)])\s+"          # bullet or numbered item
    r"(?:\[[ xX]\]\s+)?"                 # optional task-list checkbox
    r"\[([A-Za-z][A-Za-z0-9_.-]{0,31})\]"  # the id
    r"\s+(.+?)\s*$"
)


@dataclass(frozen=True)
class Criterion:
    id: str
    text: str
    digest: str  # changes when the wording changes; whitespace-insensitive


def _digest(text: str) -> str:
    normalized = " ".join(text.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def parse_criteria(text: str) -> list[Criterion]:
    text = _COMMENT.sub("", text)  # HTML comments are notes, not part of a requirement (or one)
    found: list[Criterion] = []
    seen: set[str] = set()
    for line in text.splitlines():
        m = _LINE.match(line)
        if not m:
            continue
        cid, body = m.group(1), " ".join(m.group(2).split())
        if not any(ch.isdigit() for ch in cid):
            continue
        if cid in seen:
            raise ValueError(f"duplicate requirement id {cid}")
        seen.add(cid)
        found.append(Criterion(cid, body, _digest(body)))
    if not found:
        raise ValueError("no requirements found (expected lines like '- [R1] text'; ids need a digit)")
    return found
