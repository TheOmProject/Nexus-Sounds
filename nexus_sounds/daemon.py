import argparse
import asyncio
import json
import logging
import os
import signal
import time
from pathlib import Path
from typing import Optional

try:
    import websockets
except ImportError:
    websockets = None  # type: ignore

from .alsa import resolve_device
from .config import load as load_config, save as save_config
from .events import EventFilter, PrintStateTracker
from .packs import discover_packs, get_pack, get_sound_path
from .player import Player

logger = logging.getLogger(__name__)

MOONRAKER_WS = "ws://localhost:7125/websocket"
RECONNECT_DELAYS = [5, 10, 20, 30, 60]
SPLASH_PID_FILE = Path("/run/nexus-splash/player.pid")
SPLASH_RELEASED_FILE = Path("/run/nexus-splash/released")
STATE_DIR = Path("/run/nexus-sounds")
STATE_FILE = STATE_DIR / "startup_played"


class AudioDaemon:
    def __init__(
        self,
        config_path: Path,
        packs_dir: Path,
        *,
        ws_url: Optional[str] = None,
        splash_pid_file: Optional[Path] = None,
        splash_released_file: Optional[Path] = None,
        state_file: Optional[Path] = None,
        player: Optional[Player] = None,
    ) -> None:
        self._config_path = config_path
        self._packs_dir = packs_dir
        self._ws_url = ws_url or MOONRAKER_WS
        self._splash_pid_file = splash_pid_file or SPLASH_PID_FILE
        self._splash_released_file = splash_released_file or SPLASH_RELEASED_FILE
        self._state_file = state_file or STATE_FILE
        self._config: dict = {}
        self._packs = []
        self._player = player if player is not None else Player()
        self._event_filter: Optional[EventFilter] = None
        self._state_tracker = PrintStateTracker()
        self._config_mtime: float = 0.0
        self._startup_task: Optional[asyncio.Task] = None
        self._reload_requested = False

    def _reload_config(self) -> None:
        self._config = load_config(self._config_path)
        self._packs = discover_packs(self._packs_dir)
        if self._event_filter is None:
            self._event_filter = EventFilter(self._config)
        else:
            self._event_filter.update_config(self._config)
        try:
            self._config_mtime = self._config_path.stat().st_mtime
        except OSError:
            self._config_mtime = 0.0
        logger.info("Config loaded from %s", self._config_path)

    async def run(self) -> None:
        self._reload_config()
        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGHUP, self._on_sighup)

        attempt = 0
        while True:
            try:
                await self.run_once()
                attempt = 0
            except Exception as e:
                delay = RECONNECT_DELAYS[min(attempt, len(RECONNECT_DELAYS) - 1)]
                logger.warning("WebSocket session ended (%s), retry in %ds", e, delay)
                attempt += 1
                await asyncio.sleep(delay)

    async def run_once(self) -> None:
        if websockets is None:
            raise RuntimeError("websockets package not installed")

        async with websockets.connect(self._ws_url) as ws:
            logger.info("Connected to Moonraker WebSocket")
            await self._init(ws)
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                await self._check_config_reload()
                method = msg.get("method")
                if method:
                    self._handle_notification(method, msg.get("params", {}))
                elif "result" in msg:
                    self._handle_response(msg)

    async def _init(self, ws) -> None:
        self._state_tracker.reset()
        req_id = 1
        await ws.send(json.dumps({
            "jsonrpc": "2.0",
            "method": "printer.objects.subscribe",
            "params": {"objects": {"print_stats": None}},
            "id": req_id,
        }))

    async def _check_config_reload(self) -> None:
        if self._reload_requested:
            self._reload_requested = False
            self._reload_config()
            return
        try:
            mtime = self._config_path.stat().st_mtime
        except OSError:
            return
        if mtime != self._config_mtime:
            await self._handle_preview_request()
            self._reload_config()

    async def _handle_preview_request(self) -> None:
        # Read raw JSON before merge_with_defaults strips unknown keys
        try:
            import json as _json
            raw = _json.loads(self._config_path.read_text())
        except Exception:
            return
        pr = raw.pop("_preview_request", None)
        pf = raw.pop("_preview_file", None)
        raw.pop("_preview_token", None)
        if not pr and not pf:
            return
        try:
            save_config(self._config_path, raw)
        except OSError:
            pass
        if pf:
            self._play_file(pf)
        elif pr:
            self._play_event(pr, force=True)

    def _play_file(self, filename: str) -> None:
        """Play a specific file from the active pack (for preview)."""
        from .packs import safe_path as _safe_path
        cfg = self._config
        theme = cfg.get("theme", "nexus_default")
        pack = get_pack(self._packs, theme)
        if pack is None:
            logger.warning("Sound pack %r not found for file preview", theme)
            return
        try:
            path = _safe_path(pack.pack_dir, filename)
        except ValueError:
            logger.warning("Invalid preview filename %r", filename)
            return
        if not path.exists():
            logger.warning("Preview file not found: %s", path)
            return
        device = resolve_device(cfg.get("output_device", "auto"))
        self._player.play(path, device)
        logger.info("Preview file %s via %s", filename, device)

    def _handle_notification(self, method: str, params: dict) -> None:
        if method == "notify_klippy_ready":
            self._schedule_startup()
        elif method == "notify_klippy_disconnected":
            self._on_klippy_disconnect()
        elif method == "notify_status_update":
            status = params.get("status", {}) if isinstance(params, dict) else {}
            ps = status.get("print_stats", {})
            if ps and "state" in ps:
                self._on_print_state_change(ps["state"])

    def _handle_response(self, msg: dict) -> None:
        result = msg.get("result", {})
        if "status" in result:
            ps = result["status"].get("print_stats", {})
            if ps and "state" in ps:
                self._state_tracker.set_baseline(ps["state"])

    def _on_klippy_disconnect(self) -> None:
        logger.info("Klippy disconnected")
        self._state_tracker.reset()

    def _schedule_startup(self) -> None:
        if self._startup_task and not self._startup_task.done():
            return
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        if self._state_file.exists():
            logger.debug("Startup sound already played this boot session")
            return
        self._startup_task = asyncio.ensure_future(self._play_startup_after_splash())

    async def _play_startup_after_splash(self) -> None:
        if self._splash_pid_file.exists() and not self._splash_released_file.exists():
            for _ in range(60):
                await asyncio.sleep(1.0)
                if self._splash_released_file.exists():
                    break

        self._play_event("startup")
        try:
            self._state_file.touch()
        except OSError:
            pass

    def _on_print_state_change(self, new_state: str) -> None:
        event_key = self._state_tracker.transition(new_state)
        if event_key:
            self._play_event(event_key)

    def _play_event(self, event_key: str, force: bool = False) -> None:
        cfg = self._config
        if not cfg.get("enabled", True):
            return
        if cfg.get("muted", False):
            return

        if not force:
            assert self._event_filter is not None
            if not self._event_filter.should_play(event_key):
                return

        theme = cfg.get("theme", "nexus_default")
        pack = get_pack(self._packs, theme)
        if pack is None:
            logger.warning("Sound pack %r not found", theme)
            return

        # Check per-event sound assignment; None means event is muted via UI selection
        event_sounds = cfg.get("event_sounds", {})
        if event_sounds and event_key in event_sounds:
            assigned = event_sounds[event_key]
            if assigned is None:
                logger.debug("Event %r has no sound assigned (OFF)", event_key)
                return
            from .packs import safe_path as _safe_path
            try:
                path = _safe_path(pack.pack_dir, assigned)
                if not path.exists():
                    logger.warning("Assigned sound %r not found in pack %r", assigned, theme)
                    path = get_sound_path(pack, event_key)
            except ValueError:
                logger.warning("Invalid assigned sound %r for event %r", assigned, event_key)
                path = get_sound_path(pack, event_key)
        else:
            path = get_sound_path(pack, event_key)

        if path is None:
            logger.debug("No sound for event %r in pack %r", event_key, theme)
            return

        device = resolve_device(cfg.get("output_device", "auto"))
        ok = self._player.play(path, device)
        if ok:
            if self._event_filter and not force:
                self._event_filter.mark_played(event_key)
            logger.info("Playing %s via %s", event_key, device)

    def _on_sighup(self) -> None:
        logger.info("SIGHUP received — config reload scheduled")
        self._reload_requested = True


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Nexus Sounds audio notification daemon")
    parser.add_argument(
        "--config",
        default=str(Path.home() / "nexus-sounds" / "config.json"),
        help="Path to config.json",
    )
    parser.add_argument(
        "--packs-dir",
        default=str(Path(__file__).parent.parent / "packs"),
        help="Path to packs directory",
    )
    args = parser.parse_args()
    daemon = AudioDaemon(Path(args.config), Path(args.packs_dir))
    asyncio.run(daemon.run())


if __name__ == "__main__":
    main()
