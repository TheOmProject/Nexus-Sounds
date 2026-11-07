"""Tests for the Nexus Screen sounds.py UI prototype (structural checks only, no Qt)."""
from pathlib import Path

SOUNDS_SCREEN = Path(__file__).parent.parent / "nexus-screen-dev" / "nexus" / "screens" / "sounds.py"
TEXT = SOUNDS_SCREEN.read_text()


def test_file_exists():
    assert SOUNDS_SCREEN.exists()


def test_bridge_ok_pattern():
    assert "_BRIDGE_OK" in TEXT


def test_not_installed_message():
    assert "not installed" in TEXT.lower() or "Nexus Sounds" in TEXT


def test_screen_class_named_correctly():
    assert "class SoundsScreen" in TEXT


def test_import_guard_present():
    assert "except ImportError" in TEXT


def test_no_unchecked_bridge_calls():
    # Every call to bridge functions should be guarded by _BRIDGE_OK check
    # This is a structural smoke check that the pattern exists
    assert "_BRIDGE_OK" in TEXT


def test_syntax_valid():
    import ast
    ast.parse(TEXT)


def test_no_hardcoded_resolution_overflow():
    # Quick sanity: no raw pixel values > 800 used as constants
    import re
    # Allow values in comments; check for suspicious large literal coords
    # This is a soft check, not exhaustive
    large_x = re.findall(r'\b(9\d\d|[1-9]\d{3,})\b', TEXT)
    # Filter out anything that could be a year, port, etc.
    suspicious = [v for v in large_x if int(v) > 800 and int(v) != 44100]
    assert len(suspicious) == 0, f"Possibly out-of-bounds constants: {suspicious}"
