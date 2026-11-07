import time
from pathlib import Path
from unittest.mock import patch

import pytest
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from nexus_sounds.events import EventFilter, PrintStateTracker
from nexus_sounds.config import DEFAULT_CONFIG


def _make_config(**overrides):
    cfg = dict(DEFAULT_CONFIG)
    cfg["events"] = dict(DEFAULT_CONFIG["events"])
    cfg.update(overrides)
    return cfg


def test_event_filter_enabled():
    cfg = _make_config()
    ef = EventFilter(cfg)
    assert ef.should_play("startup") is True


def test_event_filter_disabled():
    cfg = _make_config()
    cfg["events"]["startup"] = False
    ef = EventFilter(cfg)
    assert ef.should_play("startup") is False


def test_cooldown_blocks():
    cfg = _make_config()
    cfg["cooldown_seconds"] = 60.0
    ef = EventFilter(cfg)
    ef.mark_played("startup")
    assert ef.should_play("startup") is False


def test_cooldown_expires():
    cfg = _make_config()
    cfg["cooldown_seconds"] = 0.01
    ef = EventFilter(cfg)
    ef.mark_played("startup")
    time.sleep(0.02)
    assert ef.should_play("startup") is True


def test_print_state_standby_to_printing():
    t = PrintStateTracker()
    t.set_baseline("standby")
    result = t.transition("printing")
    assert result == "print_start"


def test_print_state_paused_to_printing():
    t = PrintStateTracker()
    t.set_baseline("paused")
    result = t.transition("printing")
    assert result == "print_resumed"


def test_print_state_printing_to_paused():
    t = PrintStateTracker()
    t.set_baseline("printing")
    result = t.transition("paused")
    assert result == "print_paused"


def test_print_state_to_complete():
    t = PrintStateTracker()
    t.set_baseline("printing")
    result = t.transition("complete")
    assert result == "print_complete"


def test_print_state_to_error():
    t = PrintStateTracker()
    t.set_baseline("printing")
    result = t.transition("error")
    assert result == "print_error"


def test_print_state_to_cancelled():
    t = PrintStateTracker()
    t.set_baseline("printing")
    result = t.transition("cancelled")
    assert result == "print_cancelled"


def test_baseline_no_event():
    t = PrintStateTracker()
    t.set_baseline("printing")
    assert t._state == "printing"
    # Transition to same state → None
    result = t.transition("printing")
    assert result is None


def test_same_state_no_event():
    t = PrintStateTracker()
    t.set_baseline("printing")
    result = t.transition("printing")
    assert result is None


def test_reset_on_disconnect():
    t = PrintStateTracker()
    t.set_baseline("printing")
    t.reset()
    assert t._state is None
    assert t._baseline is None
