# Sample: tip calculator

A tiny app for trying Show Your Work. `src/tip.py` has a deliberate bug in `split`, and R4 has no test.

```bash
cd examples/tip-calculator
python -m pytest tests --junitxml=report.xml   # some fail; that's the point
hermes syw import report.xml                   # or ask the agent to use syw_import
hermes syw board
```
