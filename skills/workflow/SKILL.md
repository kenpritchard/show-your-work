---
name: workflow
description: "Use when proving work meets acceptance criteria. Show Your Work board flow."
---

# Show Your Work: evidence before "done"

Use this when a task has acceptance criteria and you are about to say the work is finished.

1. **Read the board:** `syw_board(project="/abs/path")`. Requirements with `coverage: none` are untested. Say so.
2. **Link tests to requirements:** `syw_link(project, requirement="R2", test_ids=["tests.test_tip::test_split"])`. Use the exact ids the JUnit report will contain (`classname::name`).
3. **Run the tests yourself** with the normal terminal tool, writing JUnit XML, e.g. `pytest --junitxml=report.xml`. A runner exit code of 0 is not a pass. Some harnesses always exit 0.
4. **Import the report:** `syw_import(project, report_path="report.xml")`, then read the board again. Use `syw_run_detail` to see failure messages.
5. **Report honestly:** list passing, failing, untested and stale requirements. Never claim a requirement is accepted. Only the human can record a review (Desktop page, `/syw accept`, or `hermes syw accept`), and you have no tool for it.

Linking a test is a coverage claim, not proof the test checks the requirement well. Say that when it matters.
