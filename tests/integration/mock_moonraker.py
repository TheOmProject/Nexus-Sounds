"""
Deterministic Moonraker WebSocket simulator for isolated testing.

Binds to a dynamically allocated port on 127.0.0.1.  Never connects to
the production Moonraker instance.  Implements the minimum JSON-RPC
surface that nexus_sounds.daemon requires.

Compatible with websockets >= 10 and websockets >= 14/17 (new API).
"""
import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any, List, Optional

import websockets


class MockMoonrakerServer:
    """Asyncio WebSocket server that mimics the Moonraker JSON-RPC interface."""

    def __init__(self) -> None:
        self._host = "127.0.0.1"
        self._port: int = 0
        self._server = None
        self._connections: List[Any] = []
        # Initial printer state; tests may override before connecting.
        self.printer_state = "standby"
        self.klippy_ready = True

    # ── URL ───────────────────────────────────────────────────────────────────

    @property
    def ws_url(self) -> str:
        return f"ws://{self._host}:{self._port}/websocket"

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._server = await websockets.serve(
            self._handle, self._host, 0  # port 0 = OS assigns free port
        )
        sockets = self._server.sockets
        self._port = sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    # ── Notification helpers (call from tests) ────────────────────────────────

    async def emit_klippy_ready(self) -> None:
        await self._broadcast({"jsonrpc": "2.0", "method": "notify_klippy_ready", "params": []})

    async def emit_klippy_disconnected(self) -> None:
        await self._broadcast({
            "jsonrpc": "2.0",
            "method": "notify_klippy_disconnected",
            "params": [],
        })

    async def emit_print_state(self, state: str) -> None:
        self.printer_state = state
        await self._broadcast({
            "jsonrpc": "2.0",
            "method": "notify_status_update",
            "params": {"status": {"print_stats": {"state": state}}, "eventtime": 0.0},
        })

    async def _broadcast(self, msg: dict) -> None:
        raw = json.dumps(msg)
        for ws in list(self._connections):
            try:
                await ws.send(raw)
            except Exception:
                pass

    # ── Handler ───────────────────────────────────────────────────────────────

    async def _handle(self, ws: Any) -> None:
        self._connections.append(ws)
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                method = msg.get("method", "")
                req_id = msg.get("id")

                if method == "server.connection.identify":
                    await ws.send(json.dumps({
                        "jsonrpc": "2.0",
                        "result": {"connection_id": 1},
                        "id": req_id,
                    }))

                elif method == "printer.objects.subscribe":
                    await ws.send(json.dumps({
                        "jsonrpc": "2.0",
                        "result": {
                            "status": {"print_stats": {"state": self.printer_state}},
                            "eventtime": 0.0,
                        },
                        "id": req_id,
                    }))
                    if self.klippy_ready:
                        await asyncio.sleep(0)  # yield so daemon processes response first
                        await ws.send(json.dumps({
                            "jsonrpc": "2.0",
                            "method": "notify_klippy_ready",
                            "params": [],
                        }))

                elif method == "printer.objects.query":
                    await ws.send(json.dumps({
                        "jsonrpc": "2.0",
                        "result": {
                            "status": {"print_stats": {"state": self.printer_state}},
                            "eventtime": 0.0,
                        },
                        "id": req_id,
                    }))

                elif method == "printer.info":
                    await ws.send(json.dumps({
                        "jsonrpc": "2.0",
                        "result": {
                            "state": "ready" if self.klippy_ready else "startup",
                            "state_message": "",
                            "hostname": "voron",
                            "software_version": "v0.11.0",
                        },
                        "id": req_id,
                    }))
                # Unknown methods: silently ignore (real Moonraker behaviour).
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception:
            pass
        finally:
            if ws in self._connections:
                self._connections.remove(ws)


# ── pytest fixture helper ─────────────────────────────────────────────────────

@asynccontextmanager
async def mock_moonraker(**kwargs):
    """Async context manager that starts and stops a MockMoonrakerServer."""
    server = MockMoonrakerServer()
    for k, v in kwargs.items():
        setattr(server, k, v)
    await server.start()
    try:
        yield server
    finally:
        await server.stop()
