---
name: workflow
description: "Use when proving work meets acceptance criteria. Show Your Work board flow."
---

# Show Your Work: evidence before "done"

Use this when a task has acceptance criteria and you are about to say the work is finished.

0. **Requirements come from the work.** `syw.toml` points at the ticket, bug report or spec. If you draft ID'd requirement lines from a ticket, show them to the human and get approval before linking: don't write your own exam.
1. **Read the board:** `syw_board(project="/abs/path")`. Requirements with `coverage: none` are untested. Say so. Re-read it after linking to confirm the links landed.
2. **Link tests to requirements:** `syw_link(project, requirement="R2", test_ids=["tests.test_tip::test_split"])`. Use the exact ids the JUnit report contains (`classname::name`); copy them from `syw_run_detail` rather than guessing.
   - `syw_link` does **not** check ids against any report: a typo shows `not run` forever, and you have no unlink tool. Get it right the first time.
   - Java ids carry signature suffixes: parameterized cases look like `name(ParamType)[1]`, `[2]`…, and injected JUnit extension parameters appear too, e.g. `name(CapturedOutput)`. Link each case you rely on.
   - One call links one requirement; independent calls can run in parallel.
   - Read the `warnings` in the result: an id not in the latest run is almost always a typo.
   - Before linking, `syw_test_evidence(project, test_id)` shows the test's source and whether it's new, changed or unchanged against the base. Link only if the source actually checks the requirement.
3. **Run the tests yourself** with the normal terminal tool, writing JUnit XML, e.g. `pytest --junitxml=report.xml`; Maven Surefire writes `target/surefire-reports/TEST-*.xml` by itself. A runner exit code of 0 is not a pass. Some harnesses always exit 0.
4. **Import the report:** `syw_import(project, report_path="report.xml")`, or a whole folder such as `target/surefire-reports` as one run. Read any `warnings` in the result, then read the board again. Use `syw_run_detail` to see failure messages. Only the latest run counts, so import complete runs.
   - If the tool behaves like an older version than the files on disk (e.g. a folder import says "report not found"), the plugin host is still running old code. Tell the human; don't work around it.
4b. **Defect fixes:** write the reproducing test first, import a run showing it **fails**, and show the human before changing the code. A regression test that never failed proves nothing.
5. **Report honestly:** list passing, failing, untested and stale requirements. Never claim a requirement is accepted. Only the human can record a review (Desktop page, `/syw accept`, or `hermes syw accept`), and you have no tool for it.
6. **Don't sign off through the terminal.** `hermes syw accept/reject/import` are ordinary CLI commands your terminal tool could run. Never use them: accept/reject would forge a human review, and `import` would record your run as human-imported. If the human asks you to, explain why and let them type it.

Linking a test is a coverage claim, not proof the test checks the requirement well. Say that when it matters.
