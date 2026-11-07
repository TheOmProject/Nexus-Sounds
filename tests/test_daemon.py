"""Daemon unit tests — all Moonraker, ALSA, and filesystem dependencies mocked."""
import asyncio
import json
import sys
import struct
import wave
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from nexus_sounds.config import DEFAULT_CONFIG
from nexus_sounds.daemon import AudioDaemon
from nexus_sounds.events import PrintStateTracker


# ── helpers ───────────────────────────────────────────────────────────────────

def make_wav(path: Path) -> None:
    with wave.open(str(path), "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(44100)
        for _ in range(10):
            f.writeframes(struct.pack("<h", 0))


def make_daemon(tmp_path: Path, config_overrides: dict = None) -> AudioDaemon:
    """Create daemon with isolated config and packs in tmp_path."""
    packs_dir = tmp_path / "packs"
    builtin = packs_dir / "builtin" / "nexus_default"
    builtin.mkdir(parents=True)
    manifest = {
        "id": "nexus_default", "name": "Nexus Default", "version": "1.0.0",
        "author": "Test", "description": "Test",
        "sounds": {
            "startup": "startup.wav",
            "print_start": "print_start.wav",
            "print_complete": "print_complete.wav",
            "print_error": "print_error.wav",
        }
    }
    (builtin / "manifest.json").write_text(json.dumps(manifest))
    for name in manifest["sounds"].values():
        make_wav(builtin / name)

    config = dict(DEFAULT_CONFIG)
    if config_overrides:
        config.update(config_overrides)

    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))

    daemon = AudioDaemon(config_path, packs_dir)
    daemon._reload_config()
    return daemon


# ── config reload tests ───────────────────────────────────────────────────────

def test_reload_config_loads_defaults(tmp_path):
    daemon = make_daemon(tmp_path)
    assert daemon._config["volume"] == 70


def test_reload_config_mtime_stored(tmp_path):
    daemon = make_daemon(tmp_path)
    assert daemon._config_mtime > 0.0


def test_sighup_sets_reload_flag(tmp_path):
    daemon = make_daemon(tmp_path)
    assert daemon._reload_requested is False
    daemon._on_sighup()
    assert daemon._reload_requested is True


def test_check_config_reload_on_sighup(tmp_path):
    daemon = make_daemon(tmp_path)
    daemon._on_sighup()
    asyncio.run(daemon._check_config_reload())
    assert daemon._reload_requested is False  # consumed


def test_check_config_reload_on_mtime_change(tmp_path):
    daemon = make_daemon(tmp_path)
    old_mtime = daemon._config_mtime
    # Simulate an mtime change by forcing mtime to 0
    daemon._config_mtime = 0.0
    with patch.object(daemon, '_handle_preview_request', new=AsyncMock()) as mock_pr:
        asyncio.run(daemon._check_config_reload())
    assert daemon._config_mtime != 0.0
    mock_pr.assert_awaited_once()


def test_check_config_reload_no_change(tmp_path):
    daemon = make_daemon(tmp_path)
    # After make_daemon calls _reload_config(), _config_mtime matches the file.
    # Calling _check_config_reload with no change to the file and no SIGHUP
    # should NOT reload.
    reload_count = [0]
    original_reload = daemon._reload_config

    def counting_reload():
        reload_count[0] += 1
        original_reload()

    daemon._reload_config = counting_reload
    asyncio.run(daemon._check_config_reload())
    assert reload_count[0] == 0, (
        f"Expected 0 reloads but got {reload_count[0]}; "
        f"stored mtime={daemon._config_mtime}, "
        f"actual mtime={daemon._config_path.stat().st_mtime}"
    )


# ── event dispatch tests ──────────────────────────────────────────────────────

def test_play_event_disabled_master(tmp_path):
    daemon = make_daemon(tmp_path, {"enabled": False})
    with patch.object(daemon._player, 'play') as mock_play:
        daemon._play_event("startup")
    mock_play.assert_not_called()


def test_play_event_muted(tmp_path):
    daemon = make_daemon(tmp_path, {"muted": True})
    with patch.object(daemon._player, 'play') as mock_play:
        daemon._play_event("startup")
    mock_play.assert_not_called()


def test_play_event_startup_calls_player(tmp_path):
    daemon = make_daemon(tmp_path)
    with patch("nexus_sounds.daemon.resolve_device", return_value="plughw:CARD=Device,DEV=0"):
        with patch.object(daemon._player, 'play', return_value=True) as mock_play:
            daemon._play_event("startup")
    mock_play.assert_called_once()
    args = mock_play.call_args
    assert args[0][1] == "plughw:CARD=Device,DEV=0"


def test_play_event_marks_cooldown(tmp_path):
    daemon = make_daemon(tmp_path)
    with patch("nexus_sounds.daemon.resolve_device", return_value="default"):
        with patch.object(daemon._player, 'play', return_value=True):
            daemon._play_event("startup")
    # Second call blocked by cooldown
    with patch.object(daemon._player, 'play') as mock_play2:
        with patch("nexus_sounds.daemon.resolve_device", return_value="default"):
            daemon._play_event("startup")
    mock_play2.assert_not_called()


def test_play_event_force_bypasses_filter(tmp_path):
    daemon = make_daemon(tmp_path)
    # Mark as just played → cooldown active
    daemon._event_filter.mark_played("startup")
    with patch("nexus_sounds.daemon.resolve_device", return_value="default"):
        with patch.object(daemon._player, 'play', return_value=True) as mock_play:
            daemon._play_event("startup", force=True)
    mock_play.assert_called_once()


def test_play_event_missing_pack(tmp_path):
    daemon = make_daemon(tmp_path, {"theme": "nonexistent_pack"})
    with patch.object(daemon._player, 'play') as mock_play:
        daemon._play_event("startup")
    mock_play.assert_not_called()


def test_play_event_event_not_in_pack(tmp_path):
    daemon = make_daemon(tmp_path)
    # print_paused has no sound in nexus_default
    with patch("nexus_sounds.daemon.resolve_device", return_value="default"):
        with patch.object(daemon._player, 'play') as mock_play:
            daemon._play_event("print_paused")
    mock_play.assert_not_called()


# ── notification handling ─────────────────────────────────────────────────────

def test_handle_notification_klippy_ready(tmp_path):
    daemon = make_daemon(tmp_path)
    with patch.object(daemon, '_schedule_startup') as mock_sched:
        daemon._handle_notification("notify_klippy_ready", {})
    mock_sched.assert_called_once()


def test_handle_notification_klippy_disconnected(tmp_path):
    daemon = make_daemon(tmp_path)
    daemon._state_tracker.set_baseline("printing")
    daemon._handle_notification("notify_klippy_disconnected", {})
    assert daemon._state_tracker._state is None


def test_handle_notification_print_state_change(tmp_path):
    daemon = make_daemon(tmp_path)
    daemon._state_tracker.set_baseline("standby")
    with patch.object(daemon, '_play_event') as mock_play:
        daemon._handle_notification("notify_status_update", {
            "status": {"print_stats": {"state": "printing"}}
        })
    mock_play.assert_called_with("print_start")


def test_handle_notification_no_state_field(tmp_path):
    daemon = make_daemon(tmp_path)
    with patch.object(daemon, '_play_event') as mock_play:
        daemon._handle_notification("notify_status_update", {
            "status": {"print_stats": {"filename": "test.gcode"}}
        })
    mock_play.assert_not_called()


def test_handle_notification_unknown_method(tmp_path):
    daemon = make_daemon(tmp_path)
    # Should not raise
    daemon._handle_notification("unknown_method", {})


def test_handle_response_sets_baseline(tmp_path):
    daemon = make_daemon(tmp_path)
    daemon._handle_response({
        "result": {
            "status": {"print_stats": {"state": "printing"}}
        }
    })
    assert daemon._state_tracker._state == "printing"
    assert daemon._state_tracker._baseline == "printing"


def test_handle_response_no_print_stats(tmp_path):
    daemon = make_daemon(tmp_path)
    # Should not raise
    daemon._handle_response({"result": {"status": {}}})
    assert daemon._state_tracker._state is None


# ── state transition integration ──────────────────────────────────────────────

def test_state_transitions_full_print_cycle(tmp_path):
    daemon = make_daemon(tmp_path)
    daemon._state_tracker.set_baseline("standby")
    events_played = []

    def capture_event(key, force=False):
        events_played.append(key)

    daemon._play_event = capture_event

    daemon._on_print_state_change("printing")
    daemon._on_print_state_change("complete")
    assert events_played == ["print_start", "print_complete"]


def test_state_transitions_error_cycle(tmp_path):
    daemon = make_daemon(tmp_path)
    daemon._state_tracker.set_baseline("standby")
    events = []
    daemon._play_event = lambda k, force=False: events.append(k)

    daemon._on_print_state_change("printing")
    daemon._on_print_state_change("error")
    assert events == ["print_start", "print_error"]


def test_state_transitions_pause_resume(tmp_path):
    daemon = make_daemon(tmp_path)
    daemon._state_tracker.set_baseline("printing")
    events = []
    daemon._play_event = lambda k, force=False: events.append(k)

    daemon._on_print_state_change("paused")
    daemon._on_print_state_change("printing")
    assert events == ["print_paused", "print_resumed"]


def test_repeated_identical_notifications_no_duplicate(tmp_path):
    daemon = make_daemon(tmp_path)
    daemon._state_tracker.set_baseline("standby")
    events = []
    daemon._play_event = lambda k, force=False: events.append(k)

    daemon._on_print_state_change("printing")
    daemon._on_print_state_change("printing")  # duplicate
    assert events.count("print_start") == 1


def test_connection_lost_resets_state(tmp_path):
    daemon = make_daemon(tmp_path)
    daemon._state_tracker.set_baseline("printing")
    daemon._on_klippy_disconnect()
    assert daemon._state_tracker._state is None


def test_reconnect_no_false_print_start(tmp_path):
    """After reconnect, baseline is set via _handle_response — no event fired."""
    daemon = make_daemon(tmp_path)
    daemon._on_klippy_disconnect()
    events = []
    daemon._play_event = lambda k, force=False: events.append(k)
    # Reconnect: baseline set via response (not transition)
    daemon._handle_response({
        "result": {"status": {"print_stats": {"state": "printing"}}}
    })
    assert "print_start" not in events


# ── startup / splash handover ─────────────────────────────────────────────────

def test_schedule_startup_skips_if_state_file_exists(tmp_path):
    daemon = make_daemon(tmp_path)
    state_file = tmp_path / "startup_played"
    state_file.touch()
    # Set the instance attribute directly (daemon uses self._state_file, not module constant)
    daemon._state_file = state_file
    with patch.object(daemon, '_play_event') as mock_play:
        daemon._schedule_startup()
    # Task should NOT be created if STATE_FILE exists
    assert daemon._startup_task is None
    mock_play.assert_not_called()


def test_play_startup_after_splash_no_splash(tmp_path):
    """When no splash PID file exists, plays immediately."""
    daemon = make_daemon(tmp_path)
    state_file = tmp_path / "startup_played"
    played = []
    daemon._play_event = lambda k, force=False: played.append(k)

    async def run():
        with patch("nexus_sounds.daemon.SPLASH_PID_FILE", tmp_path / "player.pid"):
            with patch("nexus_sounds.daemon.SPLASH_RELEASED_FILE", tmp_path / "released"):
                with patch("nexus_sounds.daemon.STATE_FILE", state_file):
                    await daemon._play_startup_after_splash()

    asyncio.run(run())
    assert "startup" in played


def test_play_startup_after_splash_waits_for_release(tmp_path):
    """When splash PID exists but no released file, waits then plays."""
    daemon = make_daemon(tmp_path)
    pid_file = tmp_path / "player.pid"
    released_file = tmp_path / "released"
    state_file = tmp_path / "startup_played"
    pid_file.touch()
    played = []
    daemon._play_event = lambda k, force=False: played.append(k)

    call_count = [0]
    original_exists = Path.exists

    def patched_exists(self):
        if self == released_file:
            call_count[0] += 1
            if call_count[0] >= 2:
                return True  # released on second check
            return False
        return original_exists(self)

    async def run():
        with patch("nexus_sounds.daemon.SPLASH_PID_FILE", pid_file):
            with patch("nexus_sounds.daemon.SPLASH_RELEASED_FILE", released_file):
                with patch("nexus_sounds.daemon.STATE_FILE", state_file):
                    with patch("asyncio.sleep", new=AsyncMock()):
                        with patch.object(Path, "exists", patched_exists):
                            await daemon._play_startup_after_splash()

    asyncio.run(run())
    assert "startup" in played


# ── preview request ───────────────────────────────────────────────────────────

def test_handle_preview_request_plays_and_clears(tmp_path):
    daemon = make_daemon(tmp_path)
    # Write _preview_request to disk — _handle_preview_request reads raw JSON
    import json as _json
    raw = _json.loads(daemon._config_path.read_text())
    raw["_preview_request"] = "print_start"
    raw["_preview_token"] = "tok123"
    daemon._config_path.write_text(_json.dumps(raw))
    played = []
    daemon._play_event = lambda k, force=False: played.append((k, force))

    asyncio.run(daemon._handle_preview_request())

    assert ("print_start", True) in played
    # config.json should not contain _preview_request after save
    saved = _json.loads(daemon._config_path.read_text())
    assert "_preview_request" not in saved


def test_handle_preview_request_no_request(tmp_path):
    daemon = make_daemon(tmp_path)
    played = []
    daemon._play_event = lambda k, force=False: played.append(k)
    asyncio.run(daemon._handle_preview_request())
    assert played == []


# ── run_once error handling ───────────────────────────────────────────────────

def test_run_once_raises_if_websockets_unavailable(tmp_path):
    daemon = make_daemon(tmp_path)
    import nexus_sounds.daemon as daemon_mod
    orig = daemon_mod.websockets
    daemon_mod.websockets = None
    try:
        with pytest.raises(RuntimeError, match="websockets"):
            asyncio.run(daemon.run_once())
    finally:
        daemon_mod.websockets = orig
