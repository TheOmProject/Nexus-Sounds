import time
from typing import Optional

EVENTS = [
    "startup",
    "print_start",
    "print_complete",
    "print_error",
    "print_cancelled",
    "print_paused",
    "print_resumed",
]


class EventFilter:
    def __init__(self, config: dict) -> None:
        self._enabled: dict[str, bool] = {}
        self._cooldown: float = 3.0
        self._last_played: dict[str, float] = {}
        self.update_config(config)

    def update_config(self, config: dict) -> None:
        events_cfg = config.get("events", {})
        self._enabled = {k: bool(events_cfg.get(k, False)) for k in EVENTS}
        self._cooldown = float(config.get("cooldown_seconds", 3.0))

    def should_play(self, event_key: str) -> bool:
        if not self._enabled.get(event_key, False):
            return False
        last = self._last_played.get(event_key, 0.0)
        return (time.monotonic() - last) >= self._cooldown

    def mark_played(self, event_key: str) -> None:
        self._last_played[event_key] = time.monotonic()

    def reset_cooldown(self, event_key: str) -> None:
        self._last_played.pop(event_key, None)


class PrintStateTracker:
    def __init__(self) -> None:
        self._state: Optional[str] = None
        self._baseline: Optional[str] = None

    def set_baseline(self, state: str) -> None:
        self._state = state
        self._baseline = state

    def transition(self, new_state: str) -> Optional[str]:
        old = self._state
        if old == new_state:
            return None

        self._state = new_state

        if new_state == "printing":
            if old in (None, "standby", "paused"):
                if old == "paused":
                    return "print_resumed"
                return "print_start"
        if new_state == "complete":
            return "print_complete"
        if new_state == "error":
            return "print_error"
        if new_state == "cancelled":
            return "print_cancelled"
        if new_state == "paused" and old == "printing":
            return "print_paused"

        return None

    def reset(self) -> None:
        self._state = None
        self._baseline = None
