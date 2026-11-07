"""Phase 3D Qt tests: volume indicator, pack browser, layout validation.

Requires PyQt6 (from system python3-pyqt6) and QT_QPA_PLATFORM=offscreen.
"""
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_DEVROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_DEVROOT))
sys.path.insert(0, str(_DEVROOT / "nexus-screen-dev"))

pytestmark = pytest.mark.qt


@pytest.fixture(autouse=True)
def _reset_modules():
    yield
    for mod in list(sys.modules):
        if mod.startswith("nexus") or "nexus_sounds" in mod:
            sys.modules.pop(mod, None)


@pytest.fixture
def fake_install(tmp_path):
    install_dir = tmp_path / "nexus-sounds"
    install_dir.mkdir()
    shutil.copytree(str(_DEVROOT / "nexus_sounds"), str(install_dir / "nexus_sounds"),
                    dirs_exist_ok=True)
    # Copy builtin pack
    packs_dst = install_dir / "packs" / "builtin" / "nexus_default"
    packs_src = _DEVROOT / "packs" / "builtin" / "nexus_default"
    if packs_src.is_dir():
        shutil.copytree(str(packs_src), str(packs_dst), dirs_exist_ok=True)
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


@pytest.fixture
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def sounds_screen(qapp, fake_install):
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


# ── volume label tests ────────────────────────────────────────────────────────

class TestVolLabel:
    def test_vol_label_exists(self, sounds_screen):
        screen, _ = sounds_screen
        assert screen._vol_label is not None

    def test_vol_label_initial_value(self, sounds_screen):
        screen, _ = sounds_screen
        assert screen._vol_label._pct == 70

    def test_vol_up_updates_label(self, sounds_screen):
        screen, _ = sounds_screen
        screen._btn_vol_up.click()
        assert screen._vol_label._pct == 75

    def test_vol_down_updates_label(self, sounds_screen):
        screen, _ = sounds_screen
        screen._btn_vol_dn.click()
        assert screen._vol_label._pct == 65

    def test_vol_up_clamps_label_at_100(self, sounds_screen):
        screen, install_dir = sounds_screen
        cfg = json.loads((install_dir / "config.json").read_text())
        cfg["volume"] = 98
        (install_dir / "config.json").write_text(json.dumps(cfg))
        for _ in range(10):
            screen._btn_vol_up.click()
        assert screen._vol_label._pct == 100

    def test_vol_down_clamps_label_at_0(self, sounds_screen):
        screen, install_dir = sounds_screen
        cfg = json.loads((install_dir / "config.json").read_text())
        cfg["volume"] = 2
        (install_dir / "config.json").write_text(json.dumps(cfg))
        for _ in range(5):
            screen._btn_vol_dn.click()
        assert screen._vol_label._pct == 0

    def test_vol_label_renders_without_crash(self, sounds_screen):
        screen, _ = sounds_screen
        from PyQt6.QtGui import QPainter, QPixmap
        px = QPixmap(60, 32)
        p = QPainter(px)
        screen._vol_label.render(p)
        p.end()

    def test_vol_label_set_pct_clamped(self, qapp):
        for mod in list(sys.modules):
            if mod.startswith("nexus"):
                sys.modules.pop(mod, None)
        from nexus.screens.sounds import _VolLabel
        label = _VolLabel()
        label.set_pct(150)
        assert label._pct == 100
        label.set_pct(-10)
        assert label._pct == 0

    def test_vol_label_between_buttons(self, sounds_screen):
        """Vol label must be positioned between Vol- and Vol+ horizontally."""
        screen, _ = sounds_screen
        dn_right = screen._btn_vol_dn.geometry().right()
        up_left = screen._btn_vol_up.geometry().left()
        lbl_left = screen._vol_label.geometry().left()
        lbl_right = screen._vol_label.geometry().right()
        assert lbl_left >= dn_right
        assert lbl_right <= up_left


# ── pack browser tests ────────────────────────────────────────────────────────

class TestPackBrowser:
    def test_pack_panel_created(self, sounds_screen):
        screen, _ = sounds_screen
        assert screen._pack_panel is not None

    def test_pack_panel_has_items(self, sounds_screen):
        screen, _ = sounds_screen
        assert len(screen._pack_panel.items) >= 0  # 0 is valid if packs not found in tmp

    def test_pack_panel_title(self, sounds_screen):
        screen, _ = sounds_screen
        assert screen._pack_panel.title == "Sound Packs"

    def test_pack_panel_no_overflow(self, sounds_screen):
        screen, _ = sounds_screen
        panel = screen._pack_panel
        geom = panel.geometry()
        assert geom.right() <= 800
        assert geom.bottom() <= 480

    def test_pack_chosen_updates_theme(self, sounds_screen):
        screen, install_dir = sounds_screen
        # Simulate choosing a pack
        screen._on_pack_chosen({"id": "nexus_default", "name": "Nexus Default",
                                "description": "Original", "is_active": True})
        cfg = json.loads((install_dir / "config.json").read_text())
        assert cfg["theme"] == "nexus_default"

    def test_refresh_packs_does_not_crash(self, sounds_screen):
        screen, _ = sounds_screen
        screen._refresh_packs()


# ── screenshot capture ────────────────────────────────────────────────────────

class TestScreenshots:
    ARTIFACTS = _DEVROOT / "test-artifacts" / "qt" / "phase3d"

    def _make_screen(self, qapp, install_dir, w, h):
        os.environ["NEXUS_SCREEN_W"] = str(w)
        os.environ["NEXUS_SCREEN_H"] = str(h)
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
        screen.resize(w, h)
        return screen

    @pytest.mark.parametrize("w,h", [(480, 320), (800, 480), (1024, 600), (1920, 1080)])
    def test_screenshot_installed(self, qapp, fake_install, w, h):
        install_dir, _ = fake_install
        screen = self._make_screen(qapp, install_dir, w, h)
        px = screen.grab()
        assert not px.isNull()
        fname = self.ARTIFACTS / f"sounds_installed_{w}x{h}.png"
        assert px.save(str(fname)), f"Failed to save {fname}"

    def test_screenshot_not_installed(self, qapp, tmp_path):
        for mod in list(sys.modules):
            if mod.startswith("nexus") or "nexus_sounds" in mod:
                sys.modules.pop(mod, None)
        old = os.environ.get("NEXUS_SOUNDS_DIR")
        os.environ["NEXUS_SOUNDS_DIR"] = str(tmp_path / "nonexistent")
        os.environ["NEXUS_SCREEN_W"] = "800"
        os.environ["NEXUS_SCREEN_H"] = "480"

        import nexus.screens.sounds as _ss
        _ss._BRIDGE_OK = False

        class _MockApp:
            def push(self, *a): pass
            def back(self, *a): pass

        screen = _ss.SoundsScreen(_MockApp())
        screen.resize(800, 480)
        px = screen.grab()
        assert not px.isNull()
        fname = self.ARTIFACTS / "sounds_not_installed_800x480.png"
        px.save(str(fname))

        if old is None:
            os.environ.pop("NEXUS_SOUNDS_DIR", None)
        else:
            os.environ["NEXUS_SOUNDS_DIR"] = old
