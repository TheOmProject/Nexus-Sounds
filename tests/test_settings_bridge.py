import json
import os
import struct
import wave
from pathlib import Path
from unittest.mock import patch

import pytest
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import nexus_sounds.settings_bridge as bridge
from nexus_sounds.config import DEFAULT_CONFIG


def make_install_dir(tmp_path: Path) -> Path:
    d = tmp_path / "nexus-sounds"
    d.mkdir()
    (d / "packs").mkdir()
    (d / "packs" / "builtin").mkdir()
    return d


def test_is_installed_true(tmp_path):
    d = make_install_dir(tmp_path)
    with patch.dict(os.environ, {"NEXUS_SOUNDS_DIR": str(d)}):
        assert bridge.is_installed() is True


def test_is_installed_false(tmp_path):
    # Suppress both env override and home-dir fallback (production install may exist)
    with patch.dict(os.environ, {"NEXUS_SOUNDS_DIR": str(tmp_path / "nonexistent")}), \
         patch.object(Path, "home", return_value=tmp_path):
        assert bridge.is_installed() is False


def test_get_config_returns_defaults(tmp_path):
    d = make_install_dir(tmp_path)
    with patch.dict(os.environ, {"NEXUS_SOUNDS_DIR": str(d)}):
        cfg = bridge.get_config()
    assert cfg["schema_version"] == 1
    assert cfg["volume"] == 70


def test_set_enabled(tmp_path):
    d = make_install_dir(tmp_path)
    with patch.dict(os.environ, {"NEXUS_SOUNDS_DIR": str(d)}):
        result = bridge.set_enabled(False)
        assert result is True
        cfg = bridge.get_config()
    assert cfg["enabled"] is False


def test_set_volume_clamped(tmp_path):
    d = make_install_dir(tmp_path)
    with patch.dict(os.environ, {"NEXUS_SOUNDS_DIR": str(d)}):
        bridge.set_volume(150)
        cfg = bridge.get_config()
    assert cfg["volume"] == 100


def test_set_volume_negative(tmp_path):
    d = make_install_dir(tmp_path)
    with patch.dict(os.environ, {"NEXUS_SOUNDS_DIR": str(d)}):
        bridge.set_volume(-10)
        cfg = bridge.get_config()
    assert cfg["volume"] == 0


def test_set_theme(tmp_path):
    d = make_install_dir(tmp_path)
    with patch.dict(os.environ, {"NEXUS_SOUNDS_DIR": str(d)}):
        result = bridge.set_theme("nexus_default")
        assert result is True
        cfg = bridge.get_config()
    assert cfg["theme"] == "nexus_default"


def test_set_event_enabled(tmp_path):
    d = make_install_dir(tmp_path)
    with patch.dict(os.environ, {"NEXUS_SOUNDS_DIR": str(d)}):
        result = bridge.set_event_enabled("startup", False)
        assert result is True
        cfg = bridge.get_config()
    assert cfg["events"]["startup"] is False


def test_preview_sound_writes_request(tmp_path):
    d = make_install_dir(tmp_path)
    with patch.dict(os.environ, {"NEXUS_SOUNDS_DIR": str(d)}):
        result = bridge.preview_sound("startup")
        assert result is True
        cfg_path = d / "config.json"
        data = json.loads(cfg_path.read_text())
    assert data.get("_preview_request") == "startup"
    assert "_preview_token" in data


def test_all_methods_no_install(tmp_path):
    with patch.dict(os.environ, {"NEXUS_SOUNDS_DIR": str(tmp_path / "nonexistent")}), \
         patch.object(Path, "home", return_value=tmp_path):
        assert bridge.set_enabled(True) is False
        assert bridge.set_muted(True) is False
        assert bridge.set_volume(50) is False
        assert bridge.set_output_device("Device") is False
        assert bridge.set_theme("nexus_default") is False
        assert bridge.set_event_enabled("startup", False) is False
        assert bridge.preview_sound("startup") is False
        assert bridge.list_output_devices() == []
        assert bridge.list_packs() == []
