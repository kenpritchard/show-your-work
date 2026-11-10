# Show Your Work

**Your agent says it's done. Which requirements did it actually test, and have you signed off on them?**

Show Your Work is a [Hermes Agent](https://github.com/NousResearch/hermes-agent) plugin that keeps an evidence board for a project's acceptance criteria. For every requirement it shows four **separate** answers. They are never merged into one green check:

| Column | Question | Values |
|---|---|---|
| Coverage | Is any test linked to this requirement? | untested / linked |
| Outcome | What did the linked tests do in the latest imported run? | pass / fail / error / skipped / not run |
| Freshness | Have the tracked files changed since that run? | current / stale / unknown |
| Review | Has a **human** signed off? | not reviewed / accepted / rejected / review stale |

Why it exists: "the command exited 0" is not "the requirement is met". Some test harnesses exit 0 even when tests fail, a linked test may not check what the requirement says, and yesterday's pass says nothing about today's code.

**Full guide: [docs/USAGE.md](docs/USAGE.md)**: setup, test runners, reading the board, sign-off, the Desktop page, reference, limits and troubleshooting.

## Install

```bash
hermes plugins install kenpritchard/show-your-work --enable     # add -p <profile> for a named profile
hermes plugins doctor show-your-work                            # expect 4 tools registered
```

In **Hermes Desktop**: Capabilities → Plugins → **Install from Git** → `kenpritchard/show-your-work`, and tick both **Agent** and **Desktop**. That's the only way to get the board page when Desktop talks to a remote or Docker backend.

On native Windows, `hermes plugins install` can fail with `WinError 32` (a Hermes installer bug). See the [manual install](docs/USAGE.md#native-windows-installer-workaround).

After an **update**, restart the process that runs plugins. For Desktop that's the dashboard backend, not just the gateway. See [Update](docs/USAGE.md#update).

## Quickstart (5 minutes)

1. Use the requirements you already have: the ticket, bug report or spec, committed as Markdown on the branch. Give each requirement an ID with a digit (ticket checkboxes work):
   ```markdown
   # BUG-42: splitting a bill rounds each share down
   - [ ] [BUG42-1] split(100, 3) returns 33.33 per person
   - [ ] [BUG42-2] split(90, 3) still returns exactly 30.00
   ```
   Then add a `syw.toml` at the repo (or worktree) root pointing at it:
   ```toml
   criteria_file = "docs/bugs/BUG-42.md"
   tracked = ["src/**/*.py", "tests/**/*.py"]     # changes here make results stale
   base = "origin/main"                            # the review shows diffs against this
   ```
2. Ask your agent:
   > Use the show-your-work workflow on /abs/path/to/project: run the tests with `pytest --junitxml=report.xml`, import the report, link each test to the requirement it really checks (leave doubtful ones unlinked and say why), then show me the board.

   Maven, Gradle, Jest, Vitest, Go and .NET work too, see [test runners](docs/USAGE.md#4-get-junit-xml-from-your-test-runner). A folder of reports (e.g. `target/surefire-reports`) imports as one run.
3. Open **Show Your Work** in the Desktop sidebar (or `/syw`, or `hermes syw board`). Click a requirement, then a linked test, to see its code and what changed. Decide whether it really checks the requirement, then **Accept** or **Reject**.
4. Change a tracked file and results and sign-offs flip to *stale*. Rerun, re-import, re-review.
   For a defect, have the agent show you the reproducing test **failing** before it fixes anything: see the [defect workflow](docs/USAGE.md#defect-fix).
5. `/syw export` (or `hermes syw export`, or the Desktop button) writes a Markdown review report.

Or try the sample in [`examples/tip-calculator`](examples/tip-calculator): a deliberate bug, a misspellable link, and an untested requirement. It's walked through in the [guide](docs/USAGE.md#16-walkthrough-the-tip-calculator-sample).

## Surfaces

- **Agent tools:** `syw_board`, `syw_link`, `syw_import`, `syw_run_detail`, `syw_test_evidence`. There is **no tool that records a review**; the agent cannot accept its own work.
- **Slash command:** `/syw [board|accept R#|reject R#|export]`. Human-typed sign-off.
- **CLI:** `hermes syw board|show|change|import|accept|reject|export`.
- **Desktop page:** board; click a requirement, then a test, to see **the test's code and its diff** against the base branch; the change under review; Accept/Reject with a note; export.
- **Bundled skill:** `show-your-work:workflow` teaches the agent the flow.

## Disclosure

- **Reads** the `syw.toml`, the criteria file, the files matched by `tracked` (to hash them), and JUnit XML files or folders you or the agent name. All of these must be inside the project folder. Symlinks and paths outside the project are refused. Reports are capped at 5 MB per file (500 files / 50 MB per folder) and parsed with `defusedxml` (entities refused).
- **Stores** links, imported results (test ids, outcomes, failure messages up to 2,000 chars), report hashes, file-set hashes and reviews in SQLite at `<HERMES_HOME>/plugin-data/show-your-work/data.db`. Runs and reviews are append-only.
- **Writes** `show-your-work-review.md` into the project folder only when you export.
- **Runs no tests and makes no network or model calls.** The only process it starts is read-only `git` (`rev-parse`, `merge-base`, `diff`, `show`, `ls-files`) in the project folder, to show a test's source and diff when you open it for review. No telemetry.

## Limits

- A link is a coverage claim, not proof the test is adequate. That's what your review is for.
- "Human-only" sign-off means the agent's **tools** can't review. `hermes syw accept` is an ordinary terminal command, so an agent with a terminal tool could run it; the review would be recorded as `human:cli`. Treat sign-off as a strong convention, not a lock.
- One board per folder, not per branch: use a git worktree per feature or fix.
- Reviews are local records, not signatures: anyone who can write to the profile's files could edit the database.
- Freshness compares file contents. The "report is older than the code" warning compares file modification times, which copying or touching files can fool.

More in [Limits and honest caveats](docs/USAGE.md#14-limits-and-honest-caveats).

## Related plugins

[Hermes Receipts](https://github.com/iket72183-collab/hermes-receipts) and [completion-proof](https://github.com/yuanshen101/completion-proof) also produce evidence that work was done. Both capture or run their own checks. Show Your Work instead starts from the acceptance-criteria list (so untested requirements are visible), imports results from wherever the tests ran, and reserves sign-off for the human.

## Development

```bash
python -m pytest                         # unit + API tests, needs Hermes's venv packages
node tests/render_check.mjs              # renders the Desktop page with a stub React
hermes plugins validate .
```

Tested on Hermes Agent v0.23.0: Linux (WSL2 Docker), macOS, and native Windows (CLI; installer workaround needed).

MIT License.
