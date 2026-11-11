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

# Only the prefix is a regex. The body is taken with plain string operations: a lazy ``(.+?)\s*$``
# body pattern backtracks quadratically on a long run of spaces inside one line.
_LINE = re.compile(
    r"^\s*(?:[-*+]|\d+[.)])\s+"          # bullet or numbered item
    r"(?:\[[ xX]\]\s+)?"                 # optional task-list checkbox
    r"\[([A-Za-z][A-Za-z0-9_.-]{0,31})\]"  # the id
    r"(?=\s)"                            # then whitespace before the text
)


@dataclass(frozen=True)
class Criterion:
    id: str
    text: str
    digest: str  # changes when the wording changes; whitespace-insensitive


def _digest(text: str) -> str:
    normalized = " ".join(text.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def strip_comments(text: str) -> str:
    """Remove ``<!-- ... -->`` comments in one linear pass.

    Same result as ``re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)``, but that regex rescans to
    the end of the text for every unclosed ``<!--``, which is quadratic. An unclosed comment is
    kept as text, as the regex does.
    """
    out: list[str] = []
    pos = 0
    while True:
        start = text.find("<!--", pos)
        if start < 0:
            break
        end = text.find("-->", start + 4)
        if end < 0:
            break  # no later "-->" exists, so no later "<!--" can close either
        out.append(text[pos:start])
        pos = end + 3
    out.append(text[pos:])
    return "".join(out)


def parse_criteria(text: str) -> list[Criterion]:
    text = strip_comments(text)  # HTML comments are notes, not part of a requirement (or one)
    found: list[Criterion] = []
    seen: set[str] = set()
    for line in text.splitlines():
        m = _LINE.match(line)
        if not m:
            continue
        cid, body = m.group(1), " ".join(line[m.end():].split())
        if not body or not any(ch.isdigit() for ch in cid):
            continue
        if cid in seen:
            raise ValueError(f"duplicate requirement id {cid}")
        seen.add(cid)
        found.append(Criterion(cid, body, _digest(body)))
    if not found:
        raise ValueError("no requirements found (expected lines like '- [R1] text'; ids need a digit)")
    return found
