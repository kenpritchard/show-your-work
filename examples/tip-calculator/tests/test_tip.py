import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tip import split, tip, total_with_tip  # noqa: E402


def test_default_tip():
    assert tip(100) == 15.0


def test_split_evenly():
    assert split(100.0, 3) == 33.33


def test_rounds_to_cents():
    assert total_with_tip(10.01) == 11.51
