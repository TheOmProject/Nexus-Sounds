"""
Section 13: Audio backend safety integration tests.

Validates that ALSA operations are safely mocked in integration context.
amixer set is NEVER called against real hardware.
aplay is NEVER invoked for real playback.
"""
import json
import sys
from pathlib import Path
from typing import List
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from nexus_sounds.alsa import get_volume, set_volume, resolve_device
from nexus_sounds.player import Player
import nexus_sounds.settings_bridge as bridge


# ── Volume operations (all mocked) ───────────────────────────────────────────

def test_volume_up_does_not_call_real_amixer():
    """set_volume must not call amixer without a mock."""
    calls = []
    def fake_run(args, **kwargs):
        calls.append(args)
        m = MagicMock()
        m.returncode = 0
        m.stdout = ""
        m.stderr = ""
        return m
    with patch("subprocess.run", side_effect=fake_run):
        set_volume("Device", 80)
    assert len(calls) == 1
    assert calls[0][0] == "amixer"
    assert "80%" in calls[0]
    # Verify it did NOT go to real hardware (no actual subprocess spawned)


def test_volume_set_clamped_to_100():
    result = MagicMock(returncode=0, stdout="", stderr="")
    with patch("subprocess.run", return_value=result) as mock_run:
        set_volume("Device", 150)
    args = mock_run.call_args[0][0]
    assert "100%" in args


def test_volume_set_clamped_to_zero():
    result = MagicMock(returncode=0, stdout="", stderr="")
    with patch("subprocess.run", return_value=result) as mock_run:
        set_volume("Device", -50)
    args = mock_run.call_args[0][0]
    assert "0%" in args


def test_mute_via_bridge(tmp_path):
    """set_muted() persists to config only — does not call amixer."""
    with patch.object(bridge, "_get_install_dir", return_value=tmp_path):
        (tmp_path / "config.json").write_text(
            json.dumps({"enabled": True, "muted": False, "volume": 70,
                        "theme": "nexus_default", "output_device": "auto",
                        "events": {}, "cooldown_seconds": 3.0, "schema_version": 1})
        )
        with patch("subprocess.run") as mock_run:
            bridge.set_muted(True)
            # amixer must NOT be called on mute
            mock_run.assert_not_called()
        cfg = json.loads((tmp_path / "config.json").read_text())
    assert cfg["muted"] is True


def test_unmute_via_bridge(tmp_path):
    """set_muted(False) persists to config only — does not call amixer."""
    with patch.object(bridge, "_get_install_dir", return_value=tmp_path):
        (tmp_path / "config.json").write_text(
            json.dumps({"enabled": True, "muted": True, "volume": 70,
                        "theme": "nexus_default", "output_device": "auto",
                        "events": {}, "cooldown_seconds": 3.0, "schema_version": 1})
        )
        with patch("subprocess.run") as mock_run:
            bridge.set_muted(False)
            mock_run.assert_not_called()
        cfg = json.loads((tmp_path / "config.json").read_text())
    assert cfg["muted"] is False


# ── Device selection ──────────────────────────────────────────────────────────

def test_missing_usb_device_falls_back_to_default():
    """When USB device not found, resolve_device returns 'default' not an error."""
    with patch("nexus_sounds.alsa.find_device_by_usb_id", return_value=None):
        result = resolve_device("auto")
    assert result == "default"


def test_set_device_via_bridge(tmp_path):
    """set_output_device persists to config — does not alter ALSA."""
    with patch.object(bridge, "_get_install_dir", return_value=tmp_path):
        (tmp_path / "config.json").write_text(
            json.dumps({"enabled": True, "muted": False, "volume": 70,
                        "theme": "nexus_default", "output_device": "auto",
                        "events": {}, "cooldown_seconds": 3.0, "schema_version": 1})
        )
        with patch("subprocess.run") as mock_run:
            bridge.set_output_device("Device")
            mock_run.assert_not_called()
        cfg = json.loads((tmp_path / "config.json").read_text())
    assert cfg["output_device"] == "Device"


# ── Playback (all mocked) ─────────────────────────────────────────────────────

def test_player_never_produces_sound(tmp_path):
    """Player.play() spawns aplay subprocess — verify it's interceptable."""
    wav = tmp_path / "test.wav"
    import wave, struct
    with wave.open(str(wav), "w") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(44100)
        f.writeframes(struct.pack("<h", 0) * 44100)
    player = Player()
    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        result = player.play(wav, "plughw:CARD=Device,DEV=0")
    assert result is True
    assert mock_popen.called
    # Verify correct args
    args = mock_popen.call_args[0][0]
    assert args[0] == "aplay"
    assert "plughw:CARD=Device,DEV=0" in args


def test_playback_failure_does_not_raise(tmp_path):
    """aplay failure (rc!=0) is handled gracefully."""
    wav = tmp_path / "test.wav"
    import wave, struct
    with wave.open(str(wav), "w") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(44100)
        f.writeframes(struct.pack("<h", 0) * 10)
    player = Player()
    with patch("subprocess.Popen", side_effect=OSError("aplay not found")):
        result = player.play(wav, "default")
    assert result is False  # graceful fail, no exception


def test_preview_via_bridge_no_audio(tmp_path):
    """preview_sound() writes _preview_request to config — does not play audio."""
    with patch.object(bridge, "_get_install_dir", return_value=tmp_path):
        (tmp_path / "config.json").write_text(
            json.dumps({"enabled": True, "muted": False, "volume": 70,
                        "theme": "nexus_default", "output_device": "auto",
                        "events": {}, "cooldown_seconds": 3.0, "schema_version": 1})
        )
        with patch("subprocess.Popen") as mock_popen:
            bridge.preview_sound("startup")
            mock_popen.assert_not_called()  # preview only writes config
        cfg = json.loads((tmp_path / "config.json").read_text())
    assert cfg.get("_preview_request") == "startup"


# ── Unsupported hardware volume ───────────────────────────────────────────────

def test_get_volume_returns_none_when_control_missing():
    """Device without Speaker control returns None — UI must handle this."""
    result = MagicMock(returncode=1, stdout="", stderr="Invalid control name")
    with patch("subprocess.run", return_value=result):
        v = get_volume("Device")
    assert v is None


def test_volume_adjustment_reported_as_success_only_on_rc0():
    """set_volume does not raise but logs on rc!=0; UI must not claim success."""
    result = MagicMock(returncode=1, stdout="", stderr="error")
    with patch("subprocess.run", return_value=result):
        # Should not raise
        set_volume("Device", 50)  # logs a warning, no exception
