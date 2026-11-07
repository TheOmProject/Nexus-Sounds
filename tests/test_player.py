import struct
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from nexus_sounds.player import Player


def make_wav(path: Path) -> None:
    with wave.open(str(path), "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(44100)
        for _ in range(100):
            f.writeframes(struct.pack("<h", 0))


def test_play_valid_file(tmp_path):
    wav = tmp_path / "test.wav"
    make_wav(wav)
    player = Player()
    mock_proc = MagicMock()
    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        result = player.play(wav, "plughw:CARD=Device,DEV=0")
    assert result is True
    args = mock_popen.call_args[0][0]
    assert "aplay" in args
    assert str(wav) in args


def test_play_missing_file(tmp_path):
    player = Player()
    result = player.play(tmp_path / "missing.wav", "default")
    assert result is False


def test_play_stops_previous(tmp_path):
    wav = tmp_path / "test.wav"
    make_wav(wav)
    player = Player()
    proc1 = MagicMock()
    proc2 = MagicMock()
    with patch("subprocess.Popen", side_effect=[proc1, proc2]):
        player.play(wav, "default")
        player.play(wav, "default")
    proc1.terminate.assert_called_once()


def test_is_playing(tmp_path):
    wav = tmp_path / "test.wav"
    make_wav(wav)
    player = Player()
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    with patch("subprocess.Popen", return_value=mock_proc):
        player.play(wav, "default")
    assert player.is_playing() is True

    mock_proc.poll.return_value = 0
    assert player.is_playing() is False


def test_validate_sound_file_valid(tmp_path):
    wav = tmp_path / "test.wav"
    make_wav(wav)
    assert Player.validate_sound_file(wav) is True


def test_validate_sound_file_missing(tmp_path):
    assert Player.validate_sound_file(tmp_path / "missing.wav") is False


def test_validate_sound_file_too_small(tmp_path):
    f = tmp_path / "tiny.wav"
    f.write_bytes(b"\x00" * 10)
    assert Player.validate_sound_file(f) is False


def test_aplay_not_found(tmp_path):
    wav = tmp_path / "test.wav"
    make_wav(wav)
    player = Player()
    with patch("subprocess.Popen", side_effect=FileNotFoundError("aplay not found")):
        result = player.play(wav, "default")
    assert result is False
