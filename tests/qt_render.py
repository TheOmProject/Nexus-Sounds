"""Qt offscreen screenshot generator for SoundsScreen at multiple resolutions.

Run with:
    QT_QPA_PLATFORM=offscreen NEXUS_SOUNDS_DIR=~/nexus-sounds-dev \
        python3 tests/qt_render.py

Generates PNG files in test-artifacts/qt/.
"""
import os
import sys
import shutil
import tempfile
from pathlib import Path

# Point to dev nexus_sounds package
_DEVROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_DEVROOT))                 # nexus_sounds package
_NS_DEV = str(_DEVROOT)
os.environ.setdefault("NEXUS_SOUNDS_DIR", _NS_DEV)

# Point to NS dev copy
_NS_DEV_SCREEN = _DEVROOT / "nexus-screen-dev"
sys.path.insert(0, str(_NS_DEV_SCREEN))

# Put a temporary nexus-sounds "install" in place so is_installed() returns True
_FAKE_INSTALL = tempfile.mkdtemp(prefix="nexus-sounds-fake-install-")
_FAKE_CONFIG_DIR = Path(_FAKE_INSTALL)
(_FAKE_CONFIG_DIR / "config.json").write_text("""{
  "schema_version": 1,
  "enabled": true,
  "volume": 70,
  "muted": false,
  "theme": "nexus_default",
  "output_device": "auto",
  "events": {
    "startup": true,
    "print_start": true,
    "print_complete": true,
    "print_error": true,
    "print_cancelled": false,
    "print_paused": false,
    "print_resumed": false
  },
  "cooldown_seconds": 3.0
}""")
# Copy nexus_sounds into fake install dir so is_installed() finds it there
shutil.copytree(str(_DEVROOT / "nexus_sounds"), str(_FAKE_CONFIG_DIR / "nexus_sounds"),
                dirs_exist_ok=True)
os.environ["NEXUS_SOUNDS_DIR"] = _FAKE_INSTALL

RESOLUTIONS = [
    (480, 320),
    (800, 480),
    (1024, 600),
    (1920, 1080),
]

OUT_DIR = _DEVROOT / "test-artifacts" / "qt"
OUT_DIR.mkdir(parents=True, exist_ok=True)

results = {}

for W, H in RESOLUTIONS:
    os.environ["NEXUS_SCREEN_W"] = str(W)
    os.environ["NEXUS_SCREEN_H"] = str(H)

    # Force reimport of config to pick up new dimensions
    for mod_name in list(sys.modules.keys()):
        if mod_name.startswith("nexus"):
            del sys.modules[mod_name]

    # Also clear the sounds bridge cache
    for mod_name in list(sys.modules.keys()):
        if "nexus_sounds" in mod_name:
            del sys.modules[mod_name]

    from PyQt6.QtWidgets import QApplication, QWidget
    from PyQt6.QtGui import QPixmap
    from PyQt6.QtCore import Qt

    app = QApplication.instance() or QApplication(sys.argv)

    from nexus import theme
    # Apply QSS stylesheet
    qss_path = _NS_DEV_SCREEN / "nexus" / "theme" / "nexus.qss"
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text())
    # Set the global background to match Nexus dark theme
    from PyQt6.QtGui import QPalette, QColor as _QC
    pal = app.palette()
    pal.setColor(QPalette.ColorRole.Window, _QC("#07080a"))
    pal.setColor(QPalette.ColorRole.WindowText, _QC("#f1f3f5"))
    app.setPalette(pal)

    # Mock app object for SoundsScreen
    class _MockApp:
        def push(self, *a): pass
        def back(self, *a): pass
        def can(self, *a): return False
        def run(self, *a): pass

    mock_app = _MockApp()

    # Render installed state
    from nexus.screens.sounds import SoundsScreen
    screen_installed = SoundsScreen(mock_app)
    screen_installed.resize(W, H)
    screen_installed.show()

    px = screen_installed.grab()
    fname = f"sounds_installed_{W}x{H}.png"
    path = OUT_DIR / fname
    saved = px.save(str(path))
    results[f"installed_{W}x{H}"] = ("SAVED" if saved else "SAVE_FAILED", str(path))
    screen_installed.close()

    # Reload with _BRIDGE_OK forced False for not-installed state (first res only)
    if W == 800 and H == 480:
        import nexus.screens.sounds as _ss_mod
        orig = _ss_mod._BRIDGE_OK
        _ss_mod._BRIDGE_OK = False
        screen_missing = SoundsScreen(mock_app)
        screen_missing.resize(W, H)
        screen_missing.show()
        px2 = screen_missing.grab()
        fname2 = f"sounds_not_installed_{W}x{H}.png"
        path2 = OUT_DIR / fname2
        saved2 = px2.save(str(path2))
        results[f"not_installed_{W}x{H}"] = ("SAVED" if saved2 else "SAVE_FAILED", str(path2))
        screen_missing.close()
        _ss_mod._BRIDGE_OK = orig

    # Clean up Qt objects before next iteration
    del screen_installed
    for mod_name in list(sys.modules.keys()):
        if mod_name.startswith("nexus") or "nexus_sounds" in mod_name:
            sys.modules.pop(mod_name, None)

shutil.rmtree(_FAKE_INSTALL, ignore_errors=True)

print("Qt offscreen render results:")
for key, (status, path) in results.items():
    size = Path(path).stat().st_size if Path(path).exists() else 0
    print(f"  {key}: {status} → {path} ({size} bytes)")
