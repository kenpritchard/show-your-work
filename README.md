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

1. In your project folder, add a `syw.toml`:
   ```toml
   criteria_file = "criteria.md"
   tracked = ["src/**/*.py", "tests/**/*.py"]     # changes here make results stale
   ```
   and a `criteria.md` with one requirement per line:
   ```markdown
   - [R1] The default tip is 15% of the bill
   - [R2] The total can be split evenly between several people
   ```
2. Ask your agent:
   > Use the show-your-work workflow on /abs/path/to/project: run the tests with `pytest --junitxml=report.xml`, import the report, link each test to the requirement it really checks (leave doubtful ones unlinked and say why), then show me the board.

   Maven, Gradle, Jest, Vitest, Go and .NET work too, see [test runners](docs/USAGE.md#4-get-junit-xml-from-your-test-runner). A folder of reports (e.g. `target/surefire-reports`) imports as one run.
3. Open **Show Your Work** in the Desktop sidebar (or `/syw`, or `hermes syw board`). Inspect failures and **Accept** or **Reject** each requirement.
4. Change a tracked file and results and sign-offs flip to *stale*. Rerun, re-import, re-review.
5. `/syw export` (or `hermes syw export`, or the Desktop button) writes a Markdown review report.

Or try the sample in [`examples/tip-calculator`](examples/tip-calculator): a deliberate bug, a misspellable link, and an untested requirement. It's walked through in the [guide](docs/USAGE.md#16-walkthrough-the-tip-calculator-sample).

## Surfaces

- **Agent tools:** `syw_board`, `syw_link`, `syw_import`, `syw_run_detail`. There is **no tool that records a review**; the agent cannot accept its own work.
- **Slash command:** `/syw [board|accept R#|reject R#|export]`. Human-typed sign-off.
- **CLI:** `hermes syw board|import|accept|reject|export`.
- **Desktop page:** board, per-requirement detail with failure messages, Accept/Reject with a note, export.
- **Bundled skill:** `show-your-work:workflow` teaches the agent the flow.

## Disclosure

- **Reads** the `syw.toml`, the criteria file, the files matched by `tracked` (to hash them), and JUnit XML files or folders you or the agent name. All of these must be inside the project folder. Symlinks and paths outside the project are refused. Reports are capped at 5 MB per file (500 files / 50 MB per folder) and parsed with `defusedxml` (entities refused).
- **Stores** links, imported results (test ids, outcomes, failure messages up to 2,000 chars), report hashes, file-set hashes and reviews in SQLite at `<HERMES_HOME>/plugin-data/show-your-work/data.db`. Runs and reviews are append-only.
- **Writes** `show-your-work-review.md` into the project folder only when you export.
- **Runs nothing.** No subprocesses, no network calls, no model calls, no telemetry.

## Limits

- A link is a coverage claim, not proof the test is adequate. That's what your review is for.
- "Human-only" sign-off means the agent's **tools** can't review. `hermes syw accept` is an ordinary terminal command, so an agent with a terminal tool could run it; the review would be recorded as `human:cli`. Treat sign-off as a strong convention, not a lock.
- Reviews are local records, not signatures: anyone who can write to the profile's files could edit the database.
- Freshness compares file contents. The "report is older than the code" warning compares file modification times, which copying or touching files can fool.

More in [Limits and honest caveats](docs/USAGE.md#14-limits-and-honest-caveats).

## Related plugins

[Hermes Receipts](https://github.com/iket72183-collab/hermes-receipts) and [completion-proof](https://github.com/yuanshen101/completion-proof) also produce evidence that work was done. Both capture or run their own checks. Show Your Work instead starts from the acceptance-criteria list (so untested requirements are visible), imports results from wherever the tests ran, and reserves sign-off for the human.

## Development

```bash
python -m pytest                         # unit + API tests, needs Hermes's venv packages
hermes plugins validate .
```

Tested on Hermes Agent v0.23.0: Linux (WSL2 Docker), macOS, and native Windows (CLI; installer workaround needed).

MIT License.
