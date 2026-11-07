import sys
from pathlib import Path

# Make the plugin package importable as `show_your_work` (core logic, no Hermes needed).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
