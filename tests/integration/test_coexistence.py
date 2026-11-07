"""
Service coexistence simulation: klipper-audio + nexus-sounds both receiving events.

Both daemons run against the SAME mock Moonraker instance.  This demonstrates
the duplicate-sound risk and validates the documented mitigation strategy.

No production Moonraker connection is made.  No audio is played.
"""
import asyncio
import json
import sys
from pathlib import Path
from typing import List, Tuple

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from nexus_sounds.config import DEFAULT_CONFIG
from nexus_sounds.daemon import AudioDaemon
from tests.integration.mock_moonraker import MockMoonrakerServer, mock_moonraker
from tests.integration.test_daemon_e2e import FakePlayer

PACKS_DIR = Path(__file__).parent.parent.parent / "packs"


def make_daemon(config_path, ws_url, state_file, label=""):
    fp = FakePlayer()
    daemon = AudioDaemon(
        config_path, PACKS_DIR,
        ws_url=ws_url,
        state_file=state_file,
        splash_pid_file=config_path.parent / f"{label}.splash.pid",
        splash_released_file=config_path.parent / f"{label}.released",
        player=fp,
    )
    daemon._reload_config()
    return daemon, fp


@pytest.mark.asyncio
async def test_both_daemons_receive_print_start(tmp_path):
    """
    Two daemons subscribed to the same Moonraker: both fire print_start.wav.
    Documents the duplicate-sound risk when klipper-audio + nexus-sounds coexist.
    """
    cfg1 = tmp_path / "ns_config.json"
    cfg2 = tmp_path / "ka_config.json"
    cfg1.write_text(json.dumps(dict(DEFAULT_CONFIG)))
    cfg2.write_text(json.dumps(dict(DEFAULT_CONFIG)))
    state1 = tmp_path / "ns_state"
    state2 = tmp_path / "ka_state"
    state1.touch()   # startup already played for both
    state2.touch()

    async with mock_moonraker(klippy_ready=False, printer_state="standby") as server:
        d1, fp1 = make_daemon(cfg1, server.ws_url, state1, "ns")
        d2, fp2 = make_daemon(cfg2, server.ws_url, state2, "ka")

        t1 = asyncio.ensure_future(d1.run_once())
        t2 = asyncio.ensure_future(d2.run_once())
        await asyncio.sleep(0.2)
        await server.emit_print_state("printing")
        await asyncio.sleep(0.2)
        t1.cancel()
        t2.cancel()
        for t in [t1, t2]:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass

    # Both daemons fire print_start — this is the documented duplicate risk.
    assert "print_start.wav" in fp1.event_names, "Nexus Sounds should fire print_start"
    assert "print_start.wav" in fp2.event_names, "klipper-audio sim should fire print_start"


@pytest.mark.asyncio
async def test_nexus_sounds_disabled_no_duplicate(tmp_path):
    """
    Mitigation: disabling Nexus Sounds while klipper-audio runs → no duplicate.
    Only klipper-audio plays; Nexus Sounds is silent.
    """
    cfg1 = tmp_path / "ns_config.json"
    cfg2 = tmp_path / "ka_config.json"
    ns_cfg = dict(DEFAULT_CONFIG)
    ns_cfg["enabled"] = False   # Nexus Sounds disabled
    cfg1.write_text(json.dumps(ns_cfg))
    cfg2.write_text(json.dumps(dict(DEFAULT_CONFIG)))
    state1 = tmp_path / "ns_state"
    state2 = tmp_path / "ka_state"
    state1.touch()
    state2.touch()

    async with mock_moonraker(klippy_ready=False, printer_state="standby") as server:
        d1, fp1 = make_daemon(cfg1, server.ws_url, state1, "ns")
        d2, fp2 = make_daemon(cfg2, server.ws_url, state2, "ka")

        t1 = asyncio.ensure_future(d1.run_once())
        t2 = asyncio.ensure_future(d2.run_once())
        await asyncio.sleep(0.2)
        await server.emit_print_state("printing")
        await asyncio.sleep(0.2)
        t1.cancel()
        t2.cancel()
        for t in [t1, t2]:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass

    assert "print_start.wav" not in fp1.event_names, "Nexus Sounds should be silent"
    assert "print_start.wav" in fp2.event_names, "klipper-audio sim should still play"


@pytest.mark.asyncio
async def test_independent_moonraker_connections(tmp_path):
    """Both daemons maintain independent WebSocket connections."""
    cfg1 = tmp_path / "cfg1.json"
    cfg2 = tmp_path / "cfg2.json"
    cfg1.write_text(json.dumps(dict(DEFAULT_CONFIG)))
    cfg2.write_text(json.dumps(dict(DEFAULT_CONFIG)))

    async with mock_moonraker(klippy_ready=False) as server:
        d1, fp1 = make_daemon(cfg1, server.ws_url, tmp_path / "s1", "d1")
        d2, fp2 = make_daemon(cfg2, server.ws_url, tmp_path / "s2", "d2")

        t1 = asyncio.ensure_future(d1.run_once())
        t2 = asyncio.ensure_future(d2.run_once())
        await asyncio.sleep(0.3)
        # Both should be connected
        assert len(server._connections) == 2, "Both daemons should be connected"
        t1.cancel()
        t2.cancel()
        for t in [t1, t2]:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
