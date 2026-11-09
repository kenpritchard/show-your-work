# Sample: tip calculator

A tiny app for trying Show Your Work. `src/tip.py` has a deliberate bug in `split`, and R4 has no test.

```bash
cp -r examples/tip-calculator /tmp/tip && cd /tmp/tip
python -m pytest tests --junitxml=report.xml   # 1 failure is expected; that's the point
hermes syw import report.xml                   # or ask the agent to use syw_import
hermes syw board
```

Then ask your agent to link the tests to R1–R3 and show the board, or follow the full walkthrough with real output in [docs/USAGE.md §16](../../docs/USAGE.md#16-walkthrough-the-tip-calculator-sample).
