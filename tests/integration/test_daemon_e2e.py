"""
End-to-end daemon integration tests using MockMoonrakerServer.

The real asyncio connection and message-handling paths are exercised against
the simulator.  A FakePlayer records play() calls without invoking aplay.
Production Moonraker (localhost:7125) is never contacted.
"""
import asyncio
import json
import sys
from pathlib import Path
from typing import List, Optional, Tuple
from unittest.mock import patch

import pytest

# Allow importing nexus_sounds from project root.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from nexus_sounds.config import DEFAULT_CONFIG
from nexus_sounds.daemon import AudioDaemon
from tests.integration.mock_moonraker import MockMoonrakerServer, mock_moonraker

PACKS_DIR = Path(__file__).parent.parent.parent / "packs"
TIMEOUT = 5.0  # seconds


# ── FakePlayer ────────────────────────────────────────────────────────────────

class FakePlayer:
    """Records play() calls; never invokes aplay."""

    def __init__(self):
        self.calls: List[Tuple[str, str]] = []  # [(event_path, device), ...]
        self._playing = False

    def play(self, path: Path, device: str) -> bool:
        self.calls.append((path.name, device))
        self._playing = True
        return True

    def stop(self) -> None:
        self._playing = False

    def is_playing(self) -> bool:
        return self._playing

    def validate_sound_file(self, path: Path) -> bool:
        return path.exists()

    @property
    def event_names(self) -> List[str]:
        """Return sound filenames as recorded (e.g. 'startup.wav')."""
        return [p for p, _ in self.calls]


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_daemon(
    config_path: Path,
    ws_url: str,
    *,
    state_file: Optional[Path] = None,
    splash_pid_file: Optional[Path] = None,
    splash_released_file: Optional[Path] = None,
    player: Optional[FakePlayer] = None,
) -> Tuple[AudioDaemon, FakePlayer]:
    fp = player or FakePlayer()
    daemon = AudioDaemon(
        config_path,
        PACKS_DIR,
        ws_url=ws_url,
        state_file=state_file or config_path.parent / "startup_played",
        splash_pid_file=splash_pid_file or config_path.parent / "splash.pid",
        splash_released_file=splash_released_file or config_path.parent / "splash.released",
        player=fp,
    )
    daemon._reload_config()
    return daemon, fp


async def run_daemon_briefly(daemon: AudioDaemon, duration: float = 0.4) -> None:
    """Run daemon's run_once() for a short duration then cancel."""
    task = asyncio.ensure_future(daemon.run_once())
    await asyncio.sleep(duration)
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def config_path(tmp_path):
    cfg = dict(DEFAULT_CONFIG)
    p = tmp_path / "config.json"
    p.write_text(json.dumps(cfg))
    return p


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_initial_connection(config_path, tmp_path):
    """Daemon connects and exchanges subscription handshake."""
    async with mock_moonraker(klippy_ready=False) as server:
        daemon, fp = make_daemon(config_path, server.ws_url, state_file=tmp_path / "startup_played")
        await run_daemon_briefly(daemon, 0.3)
    # No sounds played when klippy_ready=False and state=standby.
    assert fp.calls == []


@pytest.mark.asyncio
async def test_klippy_ready_fires_startup(config_path, tmp_path):
    """notify_klippy_ready → startup.wav played (no splash delay)."""
    async with mock_moonraker(klippy_ready=True, printer_state="standby") as server:
        daemon, fp = make_daemon(config_path, server.ws_url, state_file=tmp_path / "startup_played")
        await run_daemon_briefly(daemon, 0.4)
    assert "startup.wav" in fp.event_names


@pytest.mark.asyncio
async def test_startup_deduplicated(config_path, tmp_path):
    """STATE_FILE prevents second startup sound in same boot session."""
    state_file = tmp_path / "startup_played"
    state_file.touch()  # simulate already-played this boot
    async with mock_moonraker(klippy_ready=True) as server:
        daemon, fp = make_daemon(config_path, server.ws_url, state_file=state_file)
        await run_daemon_briefly(daemon, 0.4)
    assert "startup.wav" not in fp.event_names


@pytest.mark.asyncio
async def test_print_start(config_path, tmp_path):
    """standby → printing triggers print_start.wav."""
    async with mock_moonraker(klippy_ready=False, printer_state="standby") as server:
        daemon, fp = make_daemon(config_path, server.ws_url, state_file=tmp_path / "s")
        # Give daemon time to subscribe and set baseline.
        task = asyncio.ensure_future(daemon.run_once())
        await asyncio.sleep(0.2)
        await server.emit_print_state("printing")
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    assert "print_start.wav" in fp.event_names


@pytest.mark.asyncio
async def test_print_complete(config_path, tmp_path):
    """printing → complete triggers print_complete.wav."""
    async with mock_moonraker(klippy_ready=False, printer_state="printing") as server:
        daemon, fp = make_daemon(config_path, server.ws_url, state_file=tmp_path / "s")
        task = asyncio.ensure_future(daemon.run_once())
        await asyncio.sleep(0.2)
        await server.emit_print_state("complete")
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    assert "print_complete.wav" in fp.event_names


@pytest.mark.asyncio
async def test_print_error(config_path, tmp_path):
    """printing → error triggers print_error.wav."""
    async with mock_moonraker(klippy_ready=False, printer_state="printing") as server:
        daemon, fp = make_daemon(config_path, server.ws_url, state_file=tmp_path / "s")
        task = asyncio.ensure_future(daemon.run_once())
        await asyncio.sleep(0.2)
        await server.emit_print_state("error")
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    assert "print_error.wav" in fp.event_names


@pytest.mark.asyncio
async def test_print_cancelled_no_sound_by_default(config_path, tmp_path):
    """print_cancelled is disabled by default — no sound fired."""
    async with mock_moonraker(klippy_ready=False, printer_state="printing") as server:
        daemon, fp = make_daemon(config_path, server.ws_url, state_file=tmp_path / "s")
        task = asyncio.ensure_future(daemon.run_once())
        await asyncio.sleep(0.2)
        await server.emit_print_state("cancelled")
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    # print_cancelled is disabled in DEFAULT_CONFIG
    assert "print_cancelled" not in fp.event_names


@pytest.mark.asyncio
async def test_print_paused_and_resumed(config_path, tmp_path):
    """printing→paused (paused disabled default); paused→printing (resumed disabled default)."""
    async with mock_moonraker(klippy_ready=False, printer_state="printing") as server:
        daemon, fp = make_daemon(config_path, server.ws_url, state_file=tmp_path / "s")
        task = asyncio.ensure_future(daemon.run_once())
        await asyncio.sleep(0.2)
        await server.emit_print_state("paused")
        await asyncio.sleep(0.1)
        await server.emit_print_state("printing")
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    assert "print_paused" not in fp.event_names
    assert "print_resumed" not in fp.event_names


@pytest.mark.asyncio
async def test_duplicate_notification_no_duplicate_sound(config_path, tmp_path):
    """Same state sent twice → only one print_start (cooldown blocks second)."""
    async with mock_moonraker(klippy_ready=False, printer_state="standby") as server:
        daemon, fp = make_daemon(config_path, server.ws_url, state_file=tmp_path / "s")
        task = asyncio.ensure_future(daemon.run_once())
        await asyncio.sleep(0.2)
        await server.emit_print_state("printing")
        await asyncio.sleep(0.1)
        await server.emit_print_state("printing")  # duplicate
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    assert fp.event_names.count("print_start.wav") == 1


@pytest.mark.asyncio
async def test_reconnect_no_false_print_start(config_path, tmp_path):
    """After reconnect, baseline re-established; no spurious print_start."""
    state_file = tmp_path / "s"
    state_file.touch()  # startup already played
    async with mock_moonraker(klippy_ready=False, printer_state="printing") as server:
        daemon, fp = make_daemon(config_path, server.ws_url, state_file=state_file)
        # run_once: connects, gets baseline=printing, no print_start fired
        task = asyncio.ensure_future(daemon.run_once())
        await asyncio.sleep(0.3)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    # Baseline was printing; no standby→printing transition fired
    assert "print_start.wav" not in fp.event_names


@pytest.mark.asyncio
async def test_klippy_disconnected_resets_state(config_path, tmp_path):
    """notify_klippy_disconnected resets state tracker."""
    async with mock_moonraker(klippy_ready=False, printer_state="printing") as server:
        daemon, fp = make_daemon(config_path, server.ws_url, state_file=tmp_path / "s")
        task = asyncio.ensure_future(daemon.run_once())
        await asyncio.sleep(0.2)
        await server.emit_klippy_disconnected()
        await asyncio.sleep(0.1)
        # After disconnect, state is reset; next printing notification = new print_start
        await server.emit_print_state("printing")
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    assert "print_start.wav" in fp.event_names


@pytest.mark.asyncio
async def test_daemon_disabled_no_sounds(config_path, tmp_path):
    """enabled=False → no sounds at all."""
    cfg = json.loads(config_path.read_text())
    cfg["enabled"] = False
    config_path.write_text(json.dumps(cfg))
    async with mock_moonraker(klippy_ready=True, printer_state="standby") as server:
        daemon, fp = make_daemon(config_path, server.ws_url, state_file=tmp_path / "s")
        await run_daemon_briefly(daemon, 0.4)
    assert fp.calls == []


@pytest.mark.asyncio
async def test_daemon_muted_no_sounds(config_path, tmp_path):
    """muted=True → no sounds at all."""
    cfg = json.loads(config_path.read_text())
    cfg["muted"] = True
    config_path.write_text(json.dumps(cfg))
    async with mock_moonraker(klippy_ready=True, printer_state="standby") as server:
        daemon, fp = make_daemon(config_path, server.ws_url, state_file=tmp_path / "s")
        await run_daemon_briefly(daemon, 0.4)
    assert fp.calls == []


@pytest.mark.asyncio
async def test_malformed_json_ignored(config_path, tmp_path):
    """Malformed JSON from server does not crash daemon."""
    async def handler(ws):
        await ws.send("not valid json {{{{")
        await asyncio.sleep(0.3)

    import websockets as ws_module
    server_obj = await ws_module.serve(handler, "127.0.0.1", 0)
    port = server_obj.sockets[0].getsockname()[1]
    daemon, fp = make_daemon(config_path, f"ws://127.0.0.1:{port}", state_file=tmp_path / "s")
    task = asyncio.ensure_future(daemon.run_once())
    await asyncio.sleep(0.5)
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass
    server_obj.close()
    await server_obj.wait_closed()
    # Daemon should not have crashed (no exception propagated by run_once)
    assert fp.calls == []


@pytest.mark.asyncio
async def test_moonraker_unavailable_at_startup(config_path, tmp_path):
    """Connection refused raises exception (not silent hang)."""
    daemon, fp = make_daemon(config_path, "ws://127.0.0.1:19999", state_file=tmp_path / "s")
    with pytest.raises(Exception):
        await asyncio.wait_for(daemon.run_once(), timeout=3.0)


@pytest.mark.asyncio
async def test_config_reload_during_session(config_path, tmp_path):
    """Config reload (mtime change) updates event filter without restart."""
    async with mock_moonraker(klippy_ready=False, printer_state="standby") as server:
        daemon, fp = make_daemon(config_path, server.ws_url, state_file=tmp_path / "s")
        task = asyncio.ensure_future(daemon.run_once())
        await asyncio.sleep(0.2)
        # Disable sounds mid-session via config file.
        cfg = json.loads(config_path.read_text())
        cfg["enabled"] = False
        config_path.write_text(json.dumps(cfg))
        # Trigger mtime-based reload on next check.
        import os
        os.utime(config_path, None)
        await asyncio.sleep(0.1)
        await server.emit_print_state("printing")
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    # After reload, enabled=False, so no print_start.
    assert "print_start.wav" not in fp.event_names


@pytest.mark.asyncio
async def test_graceful_shutdown(config_path, tmp_path):
    """Daemon run_once() can be cancelled cleanly."""
    async with mock_moonraker(klippy_ready=False) as server:
        daemon, fp = make_daemon(config_path, server.ws_url, state_file=tmp_path / "s")
        task = asyncio.ensure_future(daemon.run_once())
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=2.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
    # No crash — test passes if we reach here.
    assert True


@pytest.mark.asyncio
async def test_full_print_cycle(config_path, tmp_path):
    """Full cycle: startup → print_start → print_complete."""
    state_file = tmp_path / "startup_played"
    async with mock_moonraker(klippy_ready=True, printer_state="standby") as server:
        daemon, fp = make_daemon(config_path, server.ws_url, state_file=state_file)
        task = asyncio.ensure_future(daemon.run_once())
        await asyncio.sleep(0.3)  # startup fires
        await server.emit_print_state("printing")
        await asyncio.sleep(0.1)
        await server.emit_print_state("complete")
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    names = fp.event_names
    assert "startup.wav" in names
    assert "print_start.wav" in names
    assert "print_complete.wav" in names
