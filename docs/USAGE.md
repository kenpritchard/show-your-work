# Show Your Work: usage guide

This guide covers everything you need to use the plugin day to day: installing it, pointing it at the requirements you already have (a ticket, a bug report, a spec), running the agent workflow, reading the board, signing off, and fixing the problems people actually hit. The [README](../README.md) is the short version.

Applies to **v0.1.3** on Hermes Agent **v0.23.0 or later**.

## Contents

1. [How it works](#1-how-it-works)
2. [Install, update, remove](#2-install-update-remove)
3. [Set up a project](#3-set-up-a-project)
4. [Get JUnit XML from your test runner](#4-get-junit-xml-from-your-test-runner)
5. [The workflow, step by step](#5-the-workflow-step-by-step)
6. [Reading the board](#6-reading-the-board)
7. [Reviewing and signing off](#7-reviewing-and-signing-off)
8. [The Desktop page](#8-the-desktop-page)
9. [The review report (export)](#9-the-review-report-export)
10. [Reference: agent tools](#10-reference-agent-tools)
11. [Reference: `/syw` slash command](#11-reference-syw-slash-command)
12. [Reference: `hermes syw` CLI](#12-reference-hermes-syw-cli)
13. [Where data lives](#13-where-data-lives)
14. [Limits and honest caveats](#14-limits-and-honest-caveats)
15. [Troubleshooting](#15-troubleshooting)
16. [Walkthrough: the tip-calculator sample](#16-walkthrough-the-tip-calculator-sample)

---

## 1. How it works

Show Your Work sits between "the agent says it's done" and "you agree it's done". It starts from **your list of acceptance criteria**, not from whatever the agent chose to test, so a requirement nobody tested shows up as a gap instead of disappearing.

The loop:

```
 criteria.md ──► link tests ──► run tests (JUnit XML) ──► import report ──► board ──► you accept / reject
 (you write)     (agent)        (agent, CI, or you)       (agent or you)              (you only)
                                                                    ▲
                     edit code or a requirement ────────────────────┘  results and reviews go stale
```

For each requirement the board shows four **separate** answers. They are never combined into one green check, because each one can be wrong on its own:

| Column | Question it answers | Comes from |
|---|---|---|
| **Coverage** | Has anyone claimed a test checks this? | Links (`syw_link`) |
| **Outcome** | What did those tests do in the latest imported run? | The imported JUnit XML |
| **Freshness** | Has the code changed since that run? | A hash of your tracked files |
| **Review** | Has a human signed off, and is that sign-off still valid? | You, from Desktop, `/syw`, or the CLI |

Three design rules to keep in mind:

- **The plugin never runs tests.** It imports reports from wherever the tests ran: the agent's terminal, Docker, CI, or a command you ran. That's also why "the command exited 0" never counts as a pass. Some harnesses exit 0 even when tests fail.
- **The agent can't sign off.** None of the agent tools can record a review. Sign-off comes from the human surfaces. See [§14](#14-limits-and-honest-caveats) for the one way around this and how far to trust it.
- **History is append-only.** Every import is a new run, and every review is a new record. Nothing is overwritten, so the export can show what happened and when.

## 2. Install, update, remove

Plugins are per profile. Add `-p <profile>` to any `hermes` command to target a profile other than your default.

### Install from the command line

```bash
hermes plugins install kenpritchard/show-your-work --enable
# or for a specific profile:
hermes -p myprofile plugins install kenpritchard/show-your-work --enable
```

Check it loaded:

```bash
hermes plugins doctor show-your-work     # expect "registration passed", 4 tools
hermes syw --help
```

New chat sessions now have the four `syw_*` tools, the `/syw` command, and the `show-your-work:workflow` skill.

### Install from Hermes Desktop

Capabilities → Plugins → **Install from Git**, enter `kenpritchard/show-your-work`, pick the profile, and tick **both** parts:

- **Agent**: the tools, slash command and API. These install wherever that profile's Hermes runs.
- **Desktop**: the board page. This installs into the Desktop app on the machine you're sitting at.

This matters when Desktop and Hermes are on different machines, for example Desktop on Windows talking to Hermes in Docker or over SSH. Only Install from Git puts each half in the right place. A `hermes plugins install` run on the server does not put the page into a remote Desktop.

After installing, a **Show Your Work** entry (checklist icon) appears in the Desktop sidebar.

### Native Windows: installer workaround

On Windows, `hermes plugins install` can fail with `[WinError 32] The process cannot access the file because it is being used by another process` or `[WinError 5] Access is denied`. That's a Hermes installer bug, not this plugin ([NousResearch/hermes-agent#136120](https://github.com/NousResearch/hermes-agent/issues/136120), [#136121](https://github.com/NousResearch/hermes-agent/issues/136121)). Install by hand instead:

```powershell
$p = "$env:LOCALAPPDATA\hermes\profiles\<profile>\plugins"   # default profile: $env:LOCALAPPDATA\hermes\plugins
Remove-Item "$p\.install-*" -Recurse -Force -ErrorAction SilentlyContinue   # leftovers from failed tries
git clone --depth 1 https://github.com/kenpritchard/show-your-work "$p\show-your-work"
hermes -p <profile> plugins enable show-your-work
hermes -p <profile> plugins adopt show-your-work      # registers the clone so `plugins update` works
hermes -p <profile> plugins doctor show-your-work
```

`.install-*` folders that refuse to delete are still locked. Hermes ignores folders whose names start with a dot, and a reboot frees them.

### Update

```bash
hermes -p <profile> plugins update show-your-work
hermes -p <profile> plugins list          # check the version column
```

**Then restart whatever is running the plugin.** Python loads plugin code once per process, so the files on disk can be new while the running tools are old:

| You use the plugin from | Restart this |
|---|---|
| `hermes` in a terminal | Just start a new session |
| Telegram, Discord or another gateway | `hermes gateway restart` |
| Hermes Desktop | The **dashboard backend** Desktop connects to. It keeps a long-lived *plugin host* process per profile, and that process survives gateway restarts and new Desktop sessions. Restart the dashboard service; in the official Docker image that's `/command/s6-svc -r /run/service/dashboard`. |

If an agent says "the tools are serving an old version" even though `plugins list` shows the new one, it's this. See [§15](#15-troubleshooting).

### Remove

```bash
hermes -p <profile> plugins remove show-your-work
```

Or in Desktop: Capabilities → Plugins → the trash button beside Show Your Work (with the right profile picked in the **Agent** column header). Either way removes both halves. Restart the backend afterwards to unload the code.

Your boards, links, runs and reviews stay in the profile's plugin database ([§13](#13-where-data-lives)) until you delete it.

## 3. Set up a project

A project is a folder with a `syw.toml` in it, usually the root of your repo or worktree. The `syw.toml` says two things: **where the requirements are**, and **which files count as "the code"**.

### Where the criteria come from

You shouldn't have to invent requirements for the plugin. Real work already has them, in the ticket, the bug report or the spec. **Point `criteria_file` at that document.** The plugin reads only the requirement lines and ignores everything else, so the document can stay a normal ticket or spec.

| You're working on | Point `criteria_file` at | Requirements look like |
|---|---|---|
| **A feature** | The ticket's acceptance criteria, or the feature spec, committed on the branch, e.g. `docs/features/refunds.md` | `- [AC1] A refund above the order total is rejected with 422` |
| **A defect** | The bug report, committed with the fix, e.g. `docs/bugs/BUG-42.md` | `- [BUG42-1] split(100, 3) returns 33.33 per person` |
| **A whole project** | The PRD or requirements doc, e.g. `PRD.md` | `- [REF3] Concurrent refunds with the same key create exactly one refund` |

The usual change to an existing document is adding an ID to each requirement bullet. Ticket checklists (`- [ ] ...`) and numbered lists already work, so often that's all you need: `- [ ] [AC1] ...` or `1. [AC1] ...`.

**The criteria must be a file inside the project.** The plugin can't read an issue tracker or a URL. If the requirements live in GitHub Issues, Jira or Linear, paste them into a Markdown file on the branch. That's worth doing anyway: the criteria get reviewed in the same PR as the code they describe, and the board and the code always agree on which version of the requirements was tested.

**Who writes the criteria matters.** If the agent drafts the requirements and then tests against them, it's writing its own exam. Letting the agent turn a ticket into ID'd bullets is fine, but **read and approve the wording before any linking starts**. Rewording a requirement later makes its review stale, so the board will show if it changes after you've signed off.

### Defects: write the requirements so the bug can't come back

A good defect criteria file has three kinds of line:

```markdown
# BUG-42: splitting a bill rounds each share down

Reported by Jan: splitting $100 three ways shows $33.00 each.

## Fixed when

- [BUG42-1] split(100, 3) returns 33.33 per person          <!-- the exact reported case -->
- [BUG42-2] Shares are rounded to the nearest cent, not down  <!-- the rule behind it -->
- [BUG42-3] split(90, 3) still returns exactly 30.00          <!-- nearby behaviour that must not break -->
```

1. **The reported case**, written as the expected behaviour. Its test should fail before the fix: that's your proof the test actually reproduces the bug.
2. **The rule behind it**, so the fix isn't a special case for one input.
3. **What must not regress.** Link the existing tests that cover neighbouring behaviour.

The board then tells the whole story: BUG42-1 imported as `fail` before the fix and `pass` after, on `current` code, signed off by you. See the [defect walkthrough](#5-the-workflow-step-by-step).

### `syw.toml`

```toml
criteria_file = "docs/bugs/BUG-42.md"
tracked = ["src/**/*.py", "tests/**/*.py"]
```

| Key | Default | Meaning |
|---|---|---|
| `criteria_file` | `"criteria.md"` | Path, relative to the project folder, of the Markdown file holding the requirements. |
| `tracked` | `[]` | Glob patterns, relative to the project folder, for the files whose changes should make results and reviews **stale**. `**` matches any depth. |

Rules:

- Both paths must stay **inside** the project folder. `..` and absolute paths are refused, and symlinked files are ignored.
- At most **5,000** tracked files. Narrow the patterns if you hit it.
- With `tracked = []`, nothing ever goes stale and freshness means very little. Always track at least the code under test and the tests themselves.

**Choosing `tracked`.** Track what a passing run actually depends on: the source, the tests, and config that changes behaviour. Leave out docs, build output and lock files you don't care about, because any change to a tracked file marks **every** result and review stale. Examples:

```toml
# Python
tracked = ["src/**/*.py", "tests/**/*.py", "pyproject.toml"]

# Java / Maven (multi-module: one pattern per module, or start the pattern at the module folder)
tracked = ["backend/src/main/**/*.java", "backend/src/test/**/*.java", "backend/src/main/resources/**/*"]

# TypeScript
tracked = ["src/**/*.ts", "test/**/*.ts", "package.json"]
```

Usually you leave the criteria file itself **out** of `tracked`. Changes to it are already handled: rewording a requirement makes that requirement's review stale, without marking every test result stale.

### The requirement line format

A requirement is a list item whose text starts with a bracketed **ID containing a digit**:

```markdown
- [R1] The default tip is 15% of the bill
* [REF3] Concurrent refunds with the same key create exactly one refund
+ [AUTH-2] Tokens from the wrong issuer get 401
1. [BUG42-1] split(100, 3) returns 33.33 per person
- [ ] [AC1] A refund above the order total is rejected
- [x] [AC2] Refund history shows the operator who issued it
```

- Bullets can be `-`, `*`, `+`, `1.` or `1)`, indented or not. A task-list checkbox before the ID is allowed, and ticking it doesn't change the requirement.
- IDs start with a letter, then up to 31 letters, digits, `_`, `.` or `-`, and **must contain at least one digit**. That rule is what lets the plugin read a real ticket: `- [x] reproduced locally`, `- [Note] ask Jan` and `- [Docs](https://...)` are skipped, not mistaken for requirements.
- Everything that isn't a requirement line is ignored: headings, prose, links, code blocks, other bullets.
- Duplicate IDs are an error, and so is a file with no requirements.
- **Rewording a requirement makes its review stale.** The check ignores whitespace, so reflowing a line doesn't count as a change. Changing the words does.
- **Renaming or deleting an ID orphans its links.** The board reports them as orphan links. Keep IDs stable and edit the text instead.

Write requirements so a test can check them: one behaviour per line, close to the wording of the original. Requirements no test can check, such as "has CI" or "has ADRs", are allowed. They'll stay untested, and that's an honest answer.

### Several features or fixes at once: one worktree each

A board belongs to a **folder path**, and a folder has one `syw.toml`. So for parallel work, give each piece of work its own **git worktree**:

```bash
git worktree add ../app-bug-42 -b fix/bug-42
git worktree add ../app-refunds -b feature/refunds
```

Each worktree is a different path, so each gets its own board, its own criteria file and its own runs, and none of them see the others.

> **Don't switch branches in one checkout and expect separate boards.** The board is keyed by the folder path, not the branch. Check out `feature/refunds`, then `fix/bug-42`, in the same folder, and their links, runs and reviews mix on one board. Switching branches also changes tracked files, so everything goes stale. Use one worktree per branch.

When the work is merged and the worktree removed, its board stays in the database under that path ([§13](#13-where-data-lives)). Export the review report first if you want to keep a record ([§9](#9-the-review-report-export)).

### Keeping the plugin's files out of git

Normally `syw.toml` and the criteria file should be **committed** with the work: they're part of what the PR delivers. Sometimes you don't want that, for example when evaluating someone else's repo. Exclude them locally without touching `.gitignore`:

```bash
printf 'syw.toml\ncriteria.md\nshow-your-work-review.md\n' >> "$(git rev-parse --git-path info/exclude)"
```

Use `git rev-parse --git-path info/exclude`, not `.git/info/exclude`. In a git **worktree**, `.git` is a file and the plain path fails.

## 4. Get JUnit XML from your test runner

The plugin reads standard JUnit XML (`<testsuites>` or `<testsuite>` containing `<testcase>` elements). You can import **one file**, or **a folder** of `*.xml` files as one run.

| Runner | How to get JUnit XML | Import |
|---|---|---|
| **pytest** ✔ tested | `pytest --junitxml=report.xml` | `report.xml` |
| **Maven Surefire** ✔ tested | Automatic with `mvn test` / `./mvnw test` | the folder `target/surefire-reports` |
| Maven Failsafe | Automatic with `mvn verify` | the folder `target/failsafe-reports` (its `failsafe-summary.xml` is skipped with a warning) |
| Gradle | Automatic with `gradle test` | the folder `build/test-results/test` |
| Vitest | `vitest run --reporter=junit --outputFile=report.xml` | `report.xml` |
| Jest | Add `jest-junit`, then `jest --reporters=default --reporters=jest-junit` | `junit.xml` |
| Go | `gotestsum --junitfile report.xml` (install `gotest.tools/gotestsum`) | `report.xml` |
| .NET | Add the `JunitXml.TestLogger` package, then `dotnet test --logger "junit;LogFilePath=report.xml"` | `report.xml` |

Only pytest and Maven Surefire have been tested with this plugin. The rest are the standard ways those runners produce JUnit XML.

**Test IDs.** Every result gets the ID `classname::name` (just `name` if the report has no classname):

| Runner | Example ID |
|---|---|
| pytest | `tests.test_tip::test_split_evenly` |
| JUnit 5 / Maven | `com.example.RefundIntegrationTest::concurrentSameKeyRefundsCreateExactlyOneRefund` |
| JUnit 5, parameterized | `com.example.FailureReasonTest::everyFailureReasonRoundTrips(RefundFailureReason)[3]` (one ID per case) |
| JUnit 5, test with an injected parameter | `com.example.LogTest::forgedSubjectNeverLogged(CapturedOutput)` |

Classname conventions vary by runner and reporter settings, so **don't guess IDs**. Import a run first, then read the exact IDs with `syw_run_detail` (agent) or the Desktop detail view, and link those.

**Import a complete run every time.** The board only uses the **latest** run. If you import a report that covers only some tests, every linked test missing from it shows `not run`. For Maven, import the whole reports folder, not one class's file.

Limits per import: 5 MB per file; for a folder, 500 files and 50 MB in total. Failure messages are kept up to 2,000 characters.

## 5. The workflow, step by step

You normally drive this by asking the agent. The bundled skill (`show-your-work:workflow`) teaches the agent the steps, and you can ask it to load the skill explicitly. The general flow is the same for any kind of work; the defect version below adds one step that matters.

### General flow

**Step 0: requirements.** Point `syw.toml` at the ticket, bug report or spec ([§3](#where-the-criteria-come-from)). If the agent drafts the ID'd bullets, approve them before going on.

**Step 1: check the board.**
> Show me the Show Your Work board for /path/to/project.

At the start everything is `untested`.

**Step 2: run the tests and import.** The agent runs the tests in its terminal with JUnit output, then calls `syw_import`. You can also do this part yourself and run `hermes syw import report.xml`.

**Step 3: link tests to requirements.** The agent reads the tests, uses `syw_run_detail` to get the exact IDs, and calls `syw_link` once per requirement. Ask it to be strict:

> Link a test to a requirement only if the test actually checks that requirement. Leave anything doubtful unlinked and tell me why.

Linking after importing is fine. The board recomputes from the latest run, so new links pick up the results already imported.

**Step 4: read the board together.** The agent should report passing, failing, untested and stale requirements, plus any links it doubts. It should never say anything is "accepted".

**Step 5: fix, rerun, re-import.** After a code change the old run turns **stale**. Rerun the tests and import again to get **current** results.

**Step 6: you review.** Open the board (Desktop, `/syw`, or `hermes syw board`). For each requirement, look at the linked tests and outcome and decide: **Accept** or **Reject**, with a note if useful.

**Step 7: export** the review report and attach it to the PR ([§9](#9-the-review-report-export)).

### Defect fix

The difference from a feature: **prove the test reproduces the bug before fixing it.** A regression test that never failed proves nothing.

1. **Worktree and requirements.** Create a worktree for the fix, commit the bug report as `docs/bugs/BUG-42.md` with ID'd "fixed when" lines ([§3](#defects-write-the-requirements-so-the-bug-cant-come-back)), and add `syw.toml` pointing at it.
2. **Write the reproducing test first**, with no fix yet. Run the tests, import, and link. The board must show the reported-case requirement as **`fail`**. That imported failing run stays in the history as evidence.
   - If it passes, the test doesn't reproduce the bug. Fix the test, not the code.
3. **Link the regression requirement** to the existing tests around the change. They should already pass.
4. **Fix the code.** The board turns `stale`. Rerun, import: the reported case is now **`pass`, `current`**, and the neighbours still pass.
5. **Review and sign off,** then export. The run history shows a failing run followed by a passing one on the fixed code, which is the defect's story in one table.

A prompt for steps 2–4:

> We're fixing the defect in docs/bugs/BUG-42.md, using Show Your Work on /path/to/worktree. First write a test for BUG42-1 that reproduces the bug, run the tests with JUnit output, import, link it, and show me the board. It must fail before you touch the code. Stop and show me. After I confirm, fix the code, rerun, import, link the existing tests that cover BUG42-3, and show me the board again.

The "stop and show me" is deliberate: you see the failing run with your own eyes before the fix exists.

### A feature from a ticket

> Use the show-your-work workflow on /path/to/worktree. The criteria are in docs/features/refunds.md. Run the tests with `./mvnw test`, import `backend/target/surefire-reports`, link each test to the requirement it really checks (leave doubtful ones unlinked and say why), then show me the board and list what's still untested.

Untested requirements at this point are the remaining work, not a failure of the plugin.

## 6. Reading the board

### The four columns

**Coverage**

| Value | Meaning | What to do |
|---|---|---|
| `untested` (`none` in JSON) | No test is linked. Nothing has checked this requirement. | Write a test, or accept that it isn't testable and judge it some other way. |
| `linked` | At least one test is linked. | Check that the linked tests really test the requirement. A link is a claim. |

**Outcome**: from the latest run only. With several linked tests, the **worst** one wins, in this order:

`fail` › `error` › `not run` › `skipped` › `pass`

| Value | Meaning |
|---|---|
| `pass` | Every linked test passed in the latest run. |
| `fail` / `error` | At least one linked test failed (assertion) or errored (crash, setup failure). Open the detail view to see the message. |
| `skipped` | A linked test was skipped and none failed. Skipped is **not** a pass. |
| `not run` | No run imported yet, or a linked test isn't in the latest run: a typo in the ID, a renamed test, or a partial report. |

**Freshness**: the same for every linked requirement, because it compares the whole tracked file set with the latest run.

| Value | Meaning | What to do |
|---|---|---|
| `current` | The tracked files are byte-for-byte what they were when the latest run was imported. | Nothing. |
| `stale` | A tracked file changed after the import. The results describe older code. | Rerun the tests and import again. |
| `unknown` | Either no run exists, the requirement is untested, or the report files were **older** than the newest tracked file at import time. | Rerun the tests and import a fresh report. |

The `unknown`-for-old-reports rule exists because the plugin can't tell which version of the code an old report tested. Importing yesterday's report today must not look like today's code passed. The import returns a warning when this happens.

**Review**

| Value | Meaning |
|---|---|
| `not reviewed` (`none`) | No one has signed off. |
| `accepted` / `rejected` | Your latest decision, still valid. |
| `review stale` (`stale`) | You decided, but since then the requirement's wording **or** any tracked file has changed. Look again. |

### The summary line

`30 requirements · 9 untested · 0 failing · 0 stale · 0 accepted`

- *failing* counts both `fail` and `error`.
- The agent's `syw_board` result also includes a `passing` count. The CLI and export summary lines don't yet, so count the ✅ rows.

### Board icons (CLI and `/syw`)

```
✅ R1  The default tip is 15% of the bill  [1 test(s) | pass | current | review: accepted]
```

The icon shows the **outcome only**: ✅ pass, ❌ fail or error, ⏭ skipped, `·` not run. The bracket shows coverage, outcome, freshness and review. A ✅ next to `stale` or `unknown` means the tests passed on code that may not be today's code. Read the freshness, not just the icon.

### Common patterns

| You see | It usually means |
|---|---|
| linked, `not run`, everything else `pass` | The linked ID doesn't match the report. Compare it with `syw_run_detail`. |
| Everything `stale` right after a small edit | Working as designed: any tracked change stales everything. Rerun and import. |
| `pass` + `unknown` for every requirement | You imported an old report. Rerun the tests. |
| Orphan links warning | A requirement ID was renamed or deleted in the criteria file. |
| Accepted requirements flipped to `review stale` | Code or wording changed after your sign-off. Re-review. |

## 7. Reviewing and signing off

Sign-off is yours, recorded from one of three human surfaces:

| Surface | How | Recorded reviewer |
|---|---|---|
| **Desktop page** | Click a requirement → optional note → **Accept** / **Reject** | `human:desktop` |
| **Slash command** | `/syw accept R2 fixed and rechecked` · `/syw reject R4 no input validation` | `human:slash` |
| **CLI** | `hermes syw accept R2 looks good` · `hermes syw reject R4 --project /path` | `human:cli` |

- `/syw accept` and `/syw reject` use the project of the **session's working folder**: the folder with `syw.toml`, or the nearest parent with one. To review another project, use Desktop or the CLI with `--project`.
- Notes are kept up to 1,000 characters.
- A review records the requirement's wording and the tracked-file hash at that moment. If either changes later, the review shows `review stale`. Your old decision stays in the history.
- You can accept a requirement that is failing or untested. The plugin records your judgement, it doesn't override it. The export shows the outcome next to your decision, so the reason is worth writing in the note.

## 8. The Desktop page

Open **Show Your Work** from the Desktop sidebar.

1. **Pick a project.** Buttons across the top list projects this profile has already used (any link, run or review), most recent first. A greyed-out button means its `syw.toml` is gone. To open a new project, type its absolute path in the box and press **Open**. The page remembers the last project you opened.
2. **Header line**: the latest run's ID, time, report path, who imported it (`agent-imported` or `human-imported`) and the test count.
3. **Summary counters**: requirements, untested, failing, stale, accepted by you.
4. **The table**: one row per requirement, with coloured badges for the four columns. Green is good, red is bad, amber is stale or skipped, grey is unknown or not reviewed.
5. **Click a row** to open its detail view:
   - each linked test, with its outcome and failure message, or a red note that nothing is linked
   - your last review (decision, who, when, note), and a hint if it's stale
   - a note box with **Accept** and **Reject**
6. **Export review report** writes the Markdown report into the project folder ([§9](#9-the-review-report-export)).

The page refreshes every 5 seconds, so a code edit or a new import shows up without reloading. The project path is the path **as Hermes sees it**. With Hermes in Docker or on a server, that's the server's path (e.g. `/projects/app`), not a Windows path.

## 9. The review report (export)

```
/syw export [path]          # in chat
hermes syw export [path]    # in a terminal
```

Or click **Export review report** in Desktop. It writes `show-your-work-review.md` into the project folder, overwriting the previous export. It contains:

- the project, criteria file, tracked-file count and hash
- the latest run (ID, time, report path, provenance, report hash)
- the summary line
- a table of every requirement with its linked test IDs and all four statuses
- **Failures**: every failing or erroring linked test, with its message
- **Human reviews**: each requirement's latest decision, reviewer, time and note, marked if stale
- **Run history**: the last 10 imports

It's plain Markdown, so you can attach it to a PR, commit it, or paste it into a ticket.

## 10. Reference: agent tools

All four take `project`: the **absolute** path of the folder containing `syw.toml`. Results are JSON with `"ok": true`, or `"ok": false` and an `error` message.

| Tool | Arguments | Does |
|---|---|---|
| `syw_board` | `project` | Returns the full board: summary (including `passing`), every requirement with all four statuses and per-test outcomes, the latest run, the tracked-file hash, and orphan links. Read-only. |
| `syw_link` | `project`, `requirement`, `test_ids` (1–50) | Links tests to one requirement and records them as linked by the agent. Adding a link that already exists does nothing. The requirement must exist; test IDs are **not** checked against reports. |
| `syw_import` | `project`, `report_path` | Imports a JUnit XML file or a folder of them (path relative to the project) as one new run, recorded as `agent-imported`. Returns the run ID, test count, outcome counts and `warnings` (old report, skipped non-JUnit files). |
| `syw_run_detail` | `project`, `run_id` (optional) | Returns every test result of a run (latest if omitted): ID, outcome, message. Use it to find exact test IDs. |

There is no tool to review, accept, reject, unlink or delete. Removing a wrong link currently needs a human (see [§14](#14-limits-and-honest-caveats)).

## 11. Reference: `/syw` slash command

Typed by you in a chat session. The agent can't send slash commands.

| Command | Does |
|---|---|
| `/syw` or `/syw board` | Board for the session's working folder (nearest `syw.toml` going up). |
| `/syw board <path>` | Board for another project. Quote Windows paths with single quotes: `/syw board 'C:\work\app'`. |
| `/syw accept <ID> [note]` | Accept a requirement in the working folder's project. |
| `/syw reject <ID> [note]` | Reject one. |
| `/syw export [path]` | Write the review report. |
| `/syw help` | Show this list. |

## 12. Reference: `hermes syw` CLI

Every command finds the project by starting at the given folder (default: the current one) and walking up to the nearest `syw.toml`.

```
hermes syw board  [project]                       print the board
hermes syw import <report> [--project P]          import a report or folder you ran yourself (human-imported)
hermes syw accept <ID> [note ...] [--project P]   record your sign-off
hermes syw reject <ID> [note ...] [--project P]   record a rejection
hermes syw export [project]                       write show-your-work-review.md
```

- `import` accepts a path relative to the current folder, or an absolute path inside the project. It prints the run ID, the counts and any warnings.
- Exit code 0 on success, 1 on any error, with the reason printed as `show-your-work: ...`.
- Add `-p <profile>` before `syw` to use another profile's data: `hermes -p myprofile syw board`.

## 13. Where data lives

- **Database:** SQLite at `<HERMES_HOME>/plugin-data/show-your-work/data.db`, one per profile. For example `~/.hermes/plugin-data/...`, or `~/.hermes/profiles/<name>/plugin-data/...` for a named profile. Profiles don't share boards.
- **Projects are keyed by their resolved absolute path.** Moving or renaming the project folder starts a fresh board. The old one stays in the database under the old path.
- **Tables:** `links` (can be added; removal is internal only), `runs` and `results` (append-only), `reviews` (append-only).
- **Files written into your project:** only `show-your-work-review.md`, and only when you export.
- **Nothing leaves your machine.** The plugin makes no network calls, starts no processes, calls no models and sends no telemetry.

## 14. Limits and honest caveats

These are deliberate trade-offs or known gaps. Know them before you rely on the board.

- **A link is a claim, not proof.** The plugin knows a test is linked and what it returned. It can't know whether the test checks the requirement well. That's what your review is for.
- **Freshness uses file contents; the old-report check uses file times.** Results go stale by comparing the bytes of tracked files, which is reliable. The "report older than the code" warning compares file modification times, which `cp -p`, `touch`, an unzip or a git checkout can shift either way.
- **Any tracked change stales everything.** Freshness is per project, not per requirement. Tune `tracked` to keep the noise down.
- **One board per folder, not per branch.** Use worktrees for parallel work.
- **Criteria must be a file in the project.** Issue trackers and URLs aren't read; paste the requirements into a Markdown file.
- **Only the latest run counts.** A partial report hides the results of earlier runs (they show `not run`).
- **Test IDs aren't checked when linking.** A typo shows `not run` forever. Compare with `syw_run_detail`.
- **The agent can't remove its own links.** There's no unlink tool yet.
- **Coverage is all-or-nothing.** There's no "partial" link and no note on a link. Evidence that isn't a test (CI config, a design doc) can't be linked.
- **"Human-only" sign-off is a strong convention, not a lock.** The agent tools can't review. But `hermes syw accept` is an ordinary terminal command, so an agent with a terminal tool *could* run it. The reviewer field would say `human:cli`. If that matters, read the review list in the export, or restrict the agent's terminal.
- **Reviews are local records, not signatures.** Anyone who can write to the profile's files can edit the database.
- **The CLI summary has no passing count, and the CLI shows ✅ next to `unknown` freshness.** Both are fixed in the next release; the agent board and Desktop page already show these correctly.
- **Platforms:** tested on Linux (including WSL2 and Docker), macOS, and native Windows via the CLI. The Windows installer needs the workaround in [§2](#native-windows-installer-workaround).

## 15. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `no syw.toml in <path> or any parent folder` | You're not inside a project, or passed the wrong path. Create `syw.toml` or pass the project folder. |
| `criteria file not found` / `no requirements found` | Check `criteria_file` in `syw.toml`. Requirement lines must look like `- [R1] text`, and the ID needs a digit: `[Note]` is ignored, `[N1]` counts. |
| Some ticket lines are missing from the board | They have no ID, or the ID has no digit. Add one: `- [ ] [AC3] ...`. |
| Results from another branch on the board, or everything stale after `git checkout` | The board is keyed by folder, not branch. Use one worktree per branch ([§3](#several-features-or-fixes-at-once-one-worktree-each)). |
| `duplicate requirement id R3` | Two lines use the same ID. Rename one. |
| `... must stay inside the project` | A path in `syw.toml` or the report path uses `..` or is absolute. |
| `report not found: some/folder` even though the folder exists | Your running plugin is **v0.1.0**, which only imports single files. Update, then restart the process that runs plugins ([§2 Update](#update)). |
| The agent says the tools serve an old version after an update | Same cause: a long-lived process still has the old code. With Desktop, restart the dashboard backend; a gateway restart or new session isn't enough. |
| `not valid JUnit XML: unexpected root <...>` | The file isn't a JUnit report. In a folder import, such files are skipped with a warning; if **all** files are like that you get `no JUnit reports in folder`. |
| `report refused: unsafe XML` | The report uses XML entities. Regenerate it with a standard reporter. |
| `report too large` | Over 5 MB per file (50 MB per folder). Split the run or trim captured output in the report. |
| Linked requirement shows `not run` | The ID doesn't match. In the sample, linking `tests.test_tip::test_rounding` when the real ID is `test_rounds_to_cents` does exactly this. |
| Everything is `unknown` after importing | The report is older than your code. Rerun the tests and import the new report. |
| `/syw accept` says `unknown requirement` | It looked in the project of the session's working folder, which may not be the one you meant. Use `hermes syw accept <ID> --project <path>` or Desktop. |
| Show Your Work is missing from Capabilities → Plugins | The **Agent** column lists plugins for the profile picked in that column's header, which may not be the profile you installed into. Switch it. |
| Desktop page: "Show Your Work" isn't in the sidebar | Install with **Install from Git** and tick **Desktop** ([§2](#install-from-hermes-desktop)), then make sure it's enabled under Capabilities → Plugins. |
| Desktop page shows API errors | The Agent half isn't installed or enabled on that profile, or the backend hasn't been restarted since installing. |
| Windows: `WinError 32` / `WinError 5` while installing | Hermes installer bug. Use the manual install ([§2](#native-windows-installer-workaround)). |

## 16. Walkthrough: the tip-calculator sample

The repo ships a tiny project with a deliberate bug (`split` uses integer division) and one requirement with no test. Read R2 as a defect report: "splitting a bill gives wrong shares". The output below is real, from v0.1.1.

```bash
cp -r examples/tip-calculator /tmp/tip && cd /tmp/tip
cat criteria.md
```
```
- [R1] The default tip is 15% of the bill
- [R2] The total can be split evenly between several people
- [R3] Amounts are rounded to the nearest cent
- [R4] A negative bill amount is rejected with a clear error
```

**Empty board:**
```
$ hermes syw board
4 requirements · 4 untested · 0 failing · 0 stale · 0 accepted
· R1  The default tip is 15% of the bill  [untested | not run | unknown | review: none]
...
```

**Run and import:**
```
$ python -m pytest tests --junitxml=report.xml
FAILED tests/test_tip.py::test_split_evenly - assert 33.0 == 33.33
1 failed, 2 passed

$ hermes syw import report.xml
Imported run 615b083d00b8: 3 tests {'pass': 2, 'fail': 1}
```

**Link** (normally the agent does this; `syw_run_detail` lists the real IDs). Here R3 is linked to a misspelt ID on purpose:
```
syw_link R1 → tests.test_tip::test_default_tip
syw_link R2 → tests.test_tip::test_split_evenly
syw_link R3 → tests.test_tip::test_rounding        (real ID: test_rounds_to_cents)
```
```
$ hermes syw board
4 requirements · 1 untested · 1 failing · 0 stale · 0 accepted
✅ R1  The default tip is 15% of the bill  [1 test(s) | pass | current | review: none]
❌ R2  The total can be split evenly between several people  [1 test(s) | fail | current | review: none]
· R3  Amounts are rounded to the nearest cent  [1 test(s) | not run | current | review: none]
· R4  A negative bill amount is rejected with a clear error  [untested | not run | unknown | review: none]
```

Each of the four rows tells you something different:
- R1 passed.
- R2 really fails.
- R3's link is wrong (`not run`).
- R4 has never been tested at all.

**Sign off on R1, then change the code:**
```
$ hermes syw accept R1 looks right
Recorded: R1 accepted

$ echo "# edit" >> src/tip.py
$ hermes syw board
4 requirements · 1 untested · 1 failing · 3 stale · 0 accepted
✅ R1  The default tip is 15% of the bill  [1 test(s) | pass | stale | review: stale]
...
```

The edit made the results stale and your sign-off stale. Fix `split` in `src/tip.py`, correct R3's link, rerun, import, and review again. Then `hermes syw export` writes the record.
