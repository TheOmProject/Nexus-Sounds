"""Qt interaction tests for SoundsScreen.

Uses QT_QPA_PLATFORM=offscreen to run without a display.
Requires PyQt6 from system packages (python3-pyqt6).

Run with:
    QT_QPA_PLATFORM=offscreen python3 -m pytest tests/test_qt_interaction.py -v
"""
import os
import sys
import json
import shutil
import tempfile
from pathlib import Path

import pytest

# Configure environment before Qt imports
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_DEVROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_DEVROOT))                    # nexus_sounds package
sys.path.insert(0, str(_DEVROOT / "nexus-screen-dev"))  # nexus package

pytestmark = pytest.mark.qt


@pytest.fixture(autouse=True)
def _reset_modules():
    """Clear nexus + nexus_sounds modules between tests to allow env changes."""
    yield
    for mod in list(sys.modules):
        if mod.startswith("nexus") or "nexus_sounds" in mod:
            sys.modules.pop(mod, None)


@pytest.fixture
def fake_install(tmp_path):
    """Create a temporary nexus-sounds 'install' with valid config."""
    install_dir = tmp_path / "nexus-sounds"
    install_dir.mkdir()
    shutil.copytree(str(_DEVROOT / "nexus_sounds"), str(install_dir / "nexus_sounds"),
                    dirs_exist_ok=True)
    cfg = {
        "schema_version": 1, "enabled": True, "volume": 70,
        "muted": False, "theme": "nexus_default", "output_device": "auto",
        "events": {
            "startup": True, "print_start": True, "print_complete": True,
            "print_error": True, "print_cancelled": False,
            "print_paused": False, "print_resumed": False,
        },
        "cooldown_seconds": 3.0,
    }
    (install_dir / "config.json").write_text(json.dumps(cfg))
    old_env = os.environ.get("NEXUS_SOUNDS_DIR")
    os.environ["NEXUS_SOUNDS_DIR"] = str(install_dir)
    yield install_dir, cfg
    if old_env is None:
        os.environ.pop("NEXUS_SOUNDS_DIR", None)
    else:
        os.environ["NEXUS_SOUNDS_DIR"] = old_env
    shutil.rmtree(str(install_dir), ignore_errors=True)


@pytest.fixture
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def sounds_screen(qapp, fake_install):
    """Instantiate SoundsScreen at 800×480 with nexus_sounds installed."""
    install_dir, cfg = fake_install
    os.environ["NEXUS_SCREEN_W"] = "800"
    os.environ["NEXUS_SCREEN_H"] = "480"
    for mod in list(sys.modules):
        if mod.startswith("nexus") or "nexus_sounds" in mod:
            sys.modules.pop(mod, None)
    from nexus.screens.sounds import SoundsScreen

    class _MockApp:
        def push(self, *a): pass
        def back(self, *a): pass
        def can(self, *a): return False
        def run(self, *a): pass

    screen = SoundsScreen(_MockApp())
    screen.resize(800, 480)
    return screen, install_dir


# ── basic instantiation ───────────────────────────────────────────────────────

def test_screen_instantiates(sounds_screen):
    screen, _ = sounds_screen
    assert screen is not None


def test_screen_title(sounds_screen):
    screen, _ = sounds_screen
    from nexus.screens.sounds import SoundsScreen
    assert SoundsScreen.TITLE == "Sounds"
    assert SoundsScreen.SUBTITLE == "Audio notifications"


def test_screen_has_enable_button(sounds_screen):
    screen, _ = sounds_screen
    assert screen._btn_enable is not None


def test_screen_has_mute_button(sounds_screen):
    screen, _ = sounds_screen
    assert screen._btn_mute is not None


def test_screen_has_vol_buttons(sounds_screen):
    screen, _ = sounds_screen
    assert screen._btn_vol_up is not None
    assert screen._btn_vol_dn is not None


def test_screen_has_preview_button(sounds_screen):
    screen, _ = sounds_screen
    assert screen._btn_preview is not None


def test_screen_has_7_event_buttons(sounds_screen):
    screen, _ = sounds_screen
    assert len(screen._event_buttons) == 7


# ── enable/disable toggle ─────────────────────────────────────────────────────

def test_enable_button_initial_state(sounds_screen):
    screen, _ = sounds_screen
    assert screen._btn_enable.isChecked() is True
    assert "ON" in screen._btn_enable.text()


def test_toggle_enable_off(sounds_screen):
    screen, install_dir = sounds_screen
    screen._btn_enable.click()
    assert screen._btn_enable.isChecked() is False
    assert "OFF" in screen._btn_enable.text()
    cfg = json.loads((install_dir / "config.json").read_text())
    assert cfg["enabled"] is False


def test_toggle_enable_back_on(sounds_screen):
    screen, install_dir = sounds_screen
    screen._btn_enable.click()
    screen._btn_enable.click()
    assert screen._btn_enable.isChecked() is True
    cfg = json.loads((install_dir / "config.json").read_text())
    assert cfg["enabled"] is True


# ── mute toggle ───────────────────────────────────────────────────────────────

def test_mute_button_initial_state(sounds_screen):
    screen, _ = sounds_screen
    assert screen._btn_mute.isChecked() is False
    assert screen._btn_mute.text() == "Mute"


def test_toggle_mute_on(sounds_screen):
    screen, install_dir = sounds_screen
    screen._btn_mute.click()
    assert screen._btn_mute.isChecked() is True
    assert screen._btn_mute.text() == "Muted"
    cfg = json.loads((install_dir / "config.json").read_text())
    assert cfg["muted"] is True


def test_toggle_mute_off(sounds_screen):
    screen, install_dir = sounds_screen
    screen._btn_mute.click()
    screen._btn_mute.click()
    cfg = json.loads((install_dir / "config.json").read_text())
    assert cfg["muted"] is False


# ── volume control ────────────────────────────────────────────────────────────

def test_vol_up_increases_volume(sounds_screen):
    screen, install_dir = sounds_screen
    screen._btn_vol_up.click()
    cfg = json.loads((install_dir / "config.json").read_text())
    assert cfg["volume"] == 75


def test_vol_down_decreases_volume(sounds_screen):
    screen, install_dir = sounds_screen
    screen._btn_vol_dn.click()
    cfg = json.loads((install_dir / "config.json").read_text())
    assert cfg["volume"] == 65


def test_vol_up_clamps_at_100(sounds_screen):
    screen, install_dir = sounds_screen
    # Set to 98 manually
    cfg = json.loads((install_dir / "config.json").read_text())
    cfg["volume"] = 98
    (install_dir / "config.json").write_text(json.dumps(cfg))
    for _ in range(5):
        screen._btn_vol_up.click()
    cfg2 = json.loads((install_dir / "config.json").read_text())
    assert cfg2["volume"] <= 100


def test_vol_down_clamps_at_0(sounds_screen):
    screen, install_dir = sounds_screen
    cfg = json.loads((install_dir / "config.json").read_text())
    cfg["volume"] = 2
    (install_dir / "config.json").write_text(json.dumps(cfg))
    for _ in range(5):
        screen._btn_vol_dn.click()
    cfg2 = json.loads((install_dir / "config.json").read_text())
    assert cfg2["volume"] >= 0


# ── per-event selector buttons (Phase 4C: buttons open submenu, not toggle) ───

def test_startup_event_on_by_default(sounds_screen):
    """Event button shows the assigned sound filename, not ON/OFF."""
    screen, _ = sounds_screen
    btn = screen._event_buttons["startup"]
    # Phase 4C: buttons show "Label  ►  filename.wav" — not checkable booleans
    assert "►" in btn.text()
    assert "Startup" in btn.text()


def test_print_cancelled_off_by_default(sounds_screen):
    screen, _ = sounds_screen
    btn = screen._event_buttons["print_cancelled"]
    assert "►" in btn.text()
    assert "OFF" in btn.text()


def test_toggle_event_off(sounds_screen):
    """Clicking event button navigates to EventSoundScreen (push called)."""
    screen, _ = sounds_screen
    pushed = []
    screen._app.push = lambda s: pushed.append(s)
    # Rebuild event_sound_screen so it uses the new push mock
    from nexus.screens.sounds import EventSoundScreen
    screen._event_sound_screen = EventSoundScreen(app=screen._app, parent=None)
    btn = screen._event_buttons["print_start"]
    btn.click()
    # _on_event_tap → EventSoundScreen.set_event → app.push(event_screen)
    assert len(pushed) == 1
    assert isinstance(pushed[0], EventSoundScreen)


def test_toggle_event_on(sounds_screen):
    """Clicking a disabled event button also opens EventSoundScreen."""
    screen, _ = sounds_screen
    pushed = []
    screen._app.push = lambda s: pushed.append(s)
    from nexus.screens.sounds import EventSoundScreen
    screen._event_sound_screen = EventSoundScreen(app=screen._app, parent=None)
    btn = screen._event_buttons["print_cancelled"]
    btn.click()
    assert len(pushed) == 1
    assert isinstance(pushed[0], EventSoundScreen)


# ── preview ───────────────────────────────────────────────────────────────────

def test_preview_button_writes_request(sounds_screen):
    screen, install_dir = sounds_screen
    screen._btn_preview.click()
    cfg = json.loads((install_dir / "config.json").read_text())
    assert "_preview_request" in cfg
    assert cfg["_preview_request"] == "print_complete"


# ── missing addon state ───────────────────────────────────────────────────────

def test_not_installed_no_buttons(qapp, tmp_path):
    os.environ["NEXUS_SCREEN_W"] = "800"
    os.environ["NEXUS_SCREEN_H"] = "480"
    # Clear env — nexus-sounds not at this path
    old = os.environ.get("NEXUS_SOUNDS_DIR")
    os.environ["NEXUS_SOUNDS_DIR"] = str(tmp_path / "nonexistent")
    for mod in list(sys.modules):
        if mod.startswith("nexus") or "nexus_sounds" in mod:
            sys.modules.pop(mod, None)

    from nexus.screens.sounds import SoundsScreen, _BRIDGE_OK

    class _MockApp:
        def push(self, *a): pass
        def back(self, *a): pass

    # Force _BRIDGE_OK False
    import nexus.screens.sounds as _ss
    _ss._BRIDGE_OK = False
    screen = SoundsScreen(_MockApp())
    assert screen._btn_enable is None
    assert screen._btn_mute is None
    assert len(screen._event_buttons) == 0

    if old is None:
        os.environ.pop("NEXUS_SOUNDS_DIR", None)
    else:
        os.environ["NEXUS_SOUNDS_DIR"] = old


def test_not_installed_does_not_crash(qapp, tmp_path):
    """Screen renders without raising even when addon is absent."""
    os.environ["NEXUS_SCREEN_W"] = "800"
    os.environ["NEXUS_SCREEN_H"] = "480"
    for mod in list(sys.modules):
        if mod.startswith("nexus") or "nexus_sounds" in mod:
            sys.modules.pop(mod, None)

    from PyQt6.QtGui import QPixmap
    import nexus.screens.sounds as _ss
    _ss._BRIDGE_OK = False

    class _MockApp:
        def push(self, *a): pass
        def back(self, *a): pass

    screen = _ss.SoundsScreen(_MockApp())
    screen.resize(800, 480)
    px = screen.grab()
    assert not px.isNull()


# ── on_enter refresh ──────────────────────────────────────────────────────────

def test_on_enter_refreshes_state(sounds_screen):
    screen, install_dir = sounds_screen
    # Change config externally
    cfg = json.loads((install_dir / "config.json").read_text())
    cfg["muted"] = True
    cfg["volume"] = 42
    (install_dir / "config.json").write_text(json.dumps(cfg))
    screen.on_enter()
    assert screen._btn_mute is not None
    assert screen._btn_mute.isChecked() is True


# ── layout geometry ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("w,h", [(480, 320), (800, 480), (1024, 600), (1920, 1080)])
def test_layout_no_overflow(qapp, fake_install, w, h):
    install_dir, _ = fake_install
    os.environ["NEXUS_SCREEN_W"] = str(w)
    os.environ["NEXUS_SCREEN_H"] = str(h)
    for mod in list(sys.modules):
        if mod.startswith("nexus") or "nexus_sounds" in mod:
            sys.modules.pop(mod, None)
    from nexus.screens.sounds import SoundsScreen

    class _MockApp:
        def push(self, *a): pass
        def back(self, *a): pass

    screen = SoundsScreen(_MockApp())
    screen.resize(w, h)
    for btn in [screen._btn_enable, screen._btn_mute,
                screen._btn_vol_up, screen._btn_vol_dn,
                screen._btn_preview]:
        if btn:
            geom = btn.geometry()
            assert geom.right() <= w, f"Button overflows right at {w}x{h}: {geom.right()} > {w}"
            assert geom.bottom() <= h, f"Button overflows bottom at {w}x{h}: {geom.bottom()} > {h}"
    for btn in screen._event_buttons.values():
        geom = btn.geometry()
        assert geom.right() <= w, f"Event btn overflows right at {w}x{h}"
        assert geom.bottom() <= h, f"Event btn overflows bottom at {w}x{h}"
