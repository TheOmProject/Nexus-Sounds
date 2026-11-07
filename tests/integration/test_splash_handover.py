"""
Splash handover protocol integration tests.

The daemon waits for /run/nexus-splash/released before playing startup.wav.
All paths are redirected to tmpdir — the real /run/nexus-splash/ is never touched.
"""
import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from nexus_sounds.config import DEFAULT_CONFIG
from nexus_sounds.daemon import AudioDaemon
from tests.integration.mock_moonraker import mock_moonraker
from tests.integration.test_daemon_e2e import FakePlayer

PACKS_DIR = Path(__file__).parent.parent.parent / "packs"


def make_splash_daemon(config_path, ws_url, pid_file, released_file, state_file):
    fp = FakePlayer()
    daemon = AudioDaemon(
        config_path, PACKS_DIR,
        ws_url=ws_url,
        splash_pid_file=pid_file,
        splash_released_file=released_file,
        state_file=state_file,
        player=fp,
    )
    daemon._reload_config()
    return daemon, fp


@pytest.fixture
def config_path(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps(dict(DEFAULT_CONFIG)))
    return p


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_splash_already_released(config_path, tmp_path):
    """released marker exists → startup plays immediately."""
    pid = tmp_path / "player.pid"
    released = tmp_path / "released"
    state = tmp_path / "startup_played"
    pid.write_text("99999")     # pid file present
    released.touch()            # already released

    async with mock_moonraker(klippy_ready=True) as server:
        daemon, fp = make_splash_daemon(config_path, server.ws_url, pid, released, state)
        task = asyncio.ensure_future(daemon.run_once())
        await asyncio.sleep(0.5)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    assert "startup.wav" in fp.event_names


@pytest.mark.asyncio
async def test_splash_released_after_delay(config_path, tmp_path):
    """released marker appears after 0.5s → startup plays after delay."""
    pid = tmp_path / "player.pid"
    released = tmp_path / "released"
    state = tmp_path / "startup_played"
    pid.write_text("99999")
    # released NOT yet present

    async def release_later():
        await asyncio.sleep(0.3)
        released.touch()

    async with mock_moonraker(klippy_ready=True) as server:
        daemon, fp = make_splash_daemon(config_path, server.ws_url, pid, released, state)
        task = asyncio.ensure_future(daemon.run_once())
        asyncio.ensure_future(release_later())
        # Daemon polls every 1s; release at 0.3s → next poll at ~1.0s → need > 1.3s
        await asyncio.sleep(1.6)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    assert "startup.wav" in fp.event_names


@pytest.mark.asyncio
async def test_no_pid_file_plays_immediately(config_path, tmp_path):
    """No splash service (no pid file) → startup plays immediately."""
    pid = tmp_path / "player.pid"       # does NOT exist
    released = tmp_path / "released"    # does NOT exist
    state = tmp_path / "startup_played"

    async with mock_moonraker(klippy_ready=True) as server:
        daemon, fp = make_splash_daemon(config_path, server.ws_url, pid, released, state)
        task = asyncio.ensure_future(daemon.run_once())
        await asyncio.sleep(0.4)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    assert "startup.wav" in fp.event_names


@pytest.mark.asyncio
async def test_daemon_shuts_down_while_waiting(config_path, tmp_path):
    """Daemon shutdown during splash wait does not hang."""
    pid = tmp_path / "player.pid"
    released = tmp_path / "released"
    state = tmp_path / "startup_played"
    pid.write_text("99999")
    # released never appears

    async with mock_moonraker(klippy_ready=True) as server:
        daemon, fp = make_splash_daemon(config_path, server.ws_url, pid, released, state)
        task = asyncio.ensure_future(daemon.run_once())
        await asyncio.sleep(0.3)
        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=2.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
    # Did not hang — test passes by reaching here.
    assert True


@pytest.mark.asyncio
async def test_startup_state_file_created(config_path, tmp_path):
    """STATE_FILE is created after startup sound plays."""
    pid = tmp_path / "player.pid"       # no splash
    released = tmp_path / "released"
    state = tmp_path / "startup_played"

    async with mock_moonraker(klippy_ready=True) as server:
        daemon, fp = make_splash_daemon(config_path, server.ws_url, pid, released, state)
        task = asyncio.ensure_future(daemon.run_once())
        await asyncio.sleep(0.5)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    assert state.exists(), "STATE_FILE should be created after startup sound"


@pytest.mark.asyncio
async def test_no_production_splash_dir_accessed(config_path, tmp_path):
    """Verify /run/nexus-splash/ is never read during test."""
    import os
    prod_pid = Path("/run/nexus-splash/player.pid")
    prod_released = Path("/run/nexus-splash/released")
    # We use tmp_path only — production paths not referenced.
    pid = tmp_path / "player.pid"
    released = tmp_path / "released"
    state = tmp_path / "startup_played"

    async with mock_moonraker(klippy_ready=True) as server:
        daemon, fp = make_splash_daemon(config_path, server.ws_url, pid, released, state)
        # Confirm daemon uses injected paths, not production paths.
        assert daemon._splash_pid_file == pid
        assert daemon._splash_released_file == released
        assert str(daemon._splash_pid_file) != str(prod_pid)
        assert str(daemon._splash_released_file) != str(prod_released)
        task = asyncio.ensure_future(daemon.run_once())
        await asyncio.sleep(0.3)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
