"""Parse JUnit XML test reports (pytest --junitxml, Maven Surefire, Jest/Vitest reporters...).

Uses defusedxml so a report with DTDs/entities can't expand or reach the network.
"""

from __future__ import annotations

from dataclasses import dataclass

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring

MAX_REPORT_BYTES = 5 * 1024 * 1024
MAX_MESSAGE_CHARS = 2000


@dataclass(frozen=True)
class TestResult:
    test_id: str  # "classname::name", or just "name" when there is no classname
    outcome: str  # pass | fail | error | skipped
    message: str = ""


def _test_id(case) -> str:
    name = (case.get("name") or "").strip()
    cls = (case.get("classname") or "").strip()
    return f"{cls}::{name}" if cls else name


def _outcome(case) -> tuple[str, str]:
    for tag, outcome in (("failure", "fail"), ("error", "error"), ("skipped", "skipped")):
        el = case.find(tag)
        if el is not None:
            msg = el.get("message")
            if not msg:
                lines = (el.text or "").strip().splitlines()
                msg = lines[0] if lines else ""
            return outcome, msg[:MAX_MESSAGE_CHARS]
    return "pass", ""


def parse_junit(data: bytes) -> list[TestResult]:
    if len(data) > MAX_REPORT_BYTES:
        raise ValueError(f"report too large (limit {MAX_REPORT_BYTES // (1024 * 1024)} MB)")
    try:
        root = fromstring(data, forbid_dtd=False, forbid_entities=True, forbid_external=True)
    except DefusedXmlException as exc:
        raise ValueError(f"report refused: unsafe XML ({type(exc).__name__})") from None
    except Exception as exc:  # ParseError and friends
        raise ValueError(f"not valid JUnit XML: {exc}") from None
    if root.tag not in ("testsuites", "testsuite"):
        raise ValueError(f"not valid JUnit XML: unexpected root <{root.tag}>")
    results = [
        TestResult(_test_id(case), *_outcome(case))
        for case in root.iter("testcase")
        if _test_id(case)
    ]
    if not results:
        raise ValueError("report contains no test cases")
    return results
