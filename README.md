# Show Your Work

**Your agent says it's done. Which requirements did it actually test, and have you signed off on them?**

Show Your Work is a Hermes Agent plugin that keeps an evidence board for a project's acceptance criteria. For every requirement it shows four **separate** answers. They are never merged into one green check:

| Column | Question | Values |
|---|---|---|
| Coverage | Is any test linked to this requirement? | untested / linked |
| Outcome | What did the linked tests do in the latest imported run? | pass / fail / error / skipped / not run |
| Freshness | Have the tracked files changed since that run? | current / stale / unknown |
| Review | Has a **human** signed off? | not reviewed / accepted / rejected / review stale |

Why it exists: "the command exited 0" is not "the requirement is met". Some test harnesses exit 0 even when tests fail, a linked test may not check what the requirement says, and yesterday's pass says nothing about today's code.

## How it works

1. Put a `syw.toml` and a criteria file in the project:
   ```toml
   criteria_file = "criteria.md"          # lines like:  - [R1] The default tip is 15%
   tracked = ["src/**/*.py", "tests/**/*.py"]
   ```
2. The agent links tests to requirements (`syw_link`), runs the tests the normal way with JUnit XML output (`pytest --junitxml=report.xml`), and imports the report (`syw_import`). Reports can come from anywhere: a Docker harness, CI, or a command you ran yourself.
3. You open **Show Your Work** in the Hermes Desktop sidebar (or `/syw`, or `hermes syw board`), inspect failures, and **Accept** or **Reject** each requirement.
4. Change a tracked file and results and sign-offs flip to *stale*. Edit a requirement's wording and its sign-off goes stale.
5. Export a Markdown review report (`/syw export`, `hermes syw export`, or the Desktop button).

## Surfaces

- **Agent tools:** `syw_board`, `syw_link`, `syw_import`, `syw_run_detail`. There is **no tool that records a review**; the agent cannot accept its own work.
- **Slash command:** `/syw [board|accept R#|reject R#|export]`. Human-typed sign-off.
- **CLI:** `hermes syw board|import|accept|reject|export`.
- **Desktop page:** board, per-requirement detail with failure messages, Accept/Reject with a note, export.
- **Bundled skill:** `show-your-work:workflow` teaches the agent the flow.

Try it on the sample in [`examples/tip-calculator`](examples/tip-calculator). It has a deliberate bug and one untested requirement.

## Disclosure

- **Reads** the `syw.toml`, the criteria file, the files matched by `tracked` (to hash them), and JUnit XML files you or the agent name. All of these must be inside the project folder. Symlinks and paths outside the project are refused. Reports are capped at 5 MB and parsed with `defusedxml` (DTD entities refused).
- **Stores** links, imported results (test ids, outcomes, failure messages up to 2,000 chars), report hashes, file-set hashes and reviews in SQLite at `<HERMES_HOME>/plugin-data/show-your-work/data.db`. Runs and reviews are append-only.
- **Writes** `show-your-work-review.md` into the project folder only when you export.
- **Runs nothing.** No subprocesses, no network calls, no model calls, no telemetry.
- **Limits:** a link is a coverage claim, not proof the test is adequate. A review is a local record, not a cryptographic signature: anyone with access to the profile's files could edit the database. "Human" means the sign-off came from a human surface (Desktop page, typed slash command, CLI), not the agent's tools.

## Related plugins

[Hermes Receipts](https://github.com/iket72183-collab/hermes-receipts) and [completion-proof](https://github.com/yuanshen101/completion-proof) also produce evidence that work was done. Both capture or run their own checks. Show Your Work instead starts from the acceptance-criteria list (so untested requirements are visible), imports results from wherever the tests ran, and reserves sign-off for the human.

## Development

```bash
python -m pytest            # unit + API tests, no Hermes install needed beyond its venv packages
hermes plugins validate . --install-deps
```

Tested on Hermes Agent v0.23.0 on Linux (WSL2 Docker) and macOS. Native Windows is untested.

MIT License.
