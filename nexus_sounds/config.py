import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_CONFIG: dict[str, Any] = {
    "schema_version": 1,
    "enabled": True,
    "volume": 70,
    "muted": False,
    "theme": "nexus_default",
    "output_device": "auto",
    "events": {
        "startup": True,
        "print_start": True,
        "print_complete": True,
        "print_error": True,
        "print_cancelled": False,
        "print_paused": False,
        "print_resumed": False,
    },
    "event_sounds": {
        "startup": "startup.wav",
        "print_start": "print_start.wav",
        "print_complete": "print_complete.wav",
        "print_error": "print_error.wav",
        "print_cancelled": None,
        "print_paused": None,
        "print_resumed": None,
    },
    "cooldown_seconds": 3.0,
}

_REQUIRED_EVENT_KEYS = list(DEFAULT_CONFIG["events"].keys())
_SAVE_LOCK = threading.Lock()


def load(path: Path) -> dict:
    if not path.exists():
        return merge_with_defaults({})
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data = merge_with_defaults(data)
        return _migrate(data)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("nexus_sounds config load failed (%s), using defaults: %s", path, e)
        return merge_with_defaults({})


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with _SAVE_LOCK:
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
            os.replace(tmp, path)
        except OSError:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            raise


def validate(data: dict) -> dict:
    out = dict(data)

    sv = out.get("schema_version", 1)
    if not isinstance(sv, int):
        raise ValueError(f"schema_version must be int, got {type(sv).__name__}")
    out["schema_version"] = sv

    enabled = out.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError(f"enabled must be bool, got {type(enabled).__name__}")

    volume = out.get("volume", 70)
    if not isinstance(volume, int):
        raise ValueError(f"volume must be int, got {type(volume).__name__}")
    out["volume"] = max(0, min(100, volume))

    muted = out.get("muted", False)
    if not isinstance(muted, bool):
        raise ValueError(f"muted must be bool, got {type(muted).__name__}")

    theme = out.get("theme", "nexus_default")
    if not isinstance(theme, str) or not theme:
        raise ValueError("theme must be a non-empty string")
    if "/" in theme or "\\" in theme or ".." in theme:
        raise ValueError(f"theme contains invalid path characters: {theme!r}")
    out["theme"] = theme

    output_device = out.get("output_device", "auto")
    if not isinstance(output_device, str):
        raise ValueError(f"output_device must be str, got {type(output_device).__name__}")

    events = out.get("events", {})
    if not isinstance(events, dict):
        raise ValueError("events must be a dict")
    for k, v in events.items():
        if not isinstance(v, bool):
            raise ValueError(f"events[{k!r}] must be bool, got {type(v).__name__}")

    cooldown = out.get("cooldown_seconds", 3.0)
    if not isinstance(cooldown, (int, float)):
        raise ValueError(f"cooldown_seconds must be numeric, got {type(cooldown).__name__}")
    out["cooldown_seconds"] = max(0.0, min(30.0, float(cooldown)))

    event_sounds = out.get("event_sounds", {})
    if not isinstance(event_sounds, dict):
        raise ValueError("event_sounds must be a dict")
    for k, v in event_sounds.items():
        if v is not None:
            if not isinstance(v, str) or not v:
                raise ValueError(f"event_sounds[{k!r}] must be None or a non-empty string")
            if "/" in v or "\\" in v or ".." in v:
                raise ValueError(f"event_sounds[{k!r}] contains invalid path characters: {v!r}")

    return out


def merge_with_defaults(data: dict) -> dict:
    result = dict(DEFAULT_CONFIG)
    result.update({k: v for k, v in data.items() if k in DEFAULT_CONFIG})

    # Merge events sub-dict
    merged_events = dict(DEFAULT_CONFIG["events"])
    if "events" in data and isinstance(data["events"], dict):
        for k, v in data["events"].items():
            if k in merged_events:
                merged_events[k] = v
    result["events"] = merged_events

    # Merge event_sounds sub-dict (values may be None)
    merged_sounds = dict(DEFAULT_CONFIG["event_sounds"])
    if "event_sounds" in data and isinstance(data["event_sounds"], dict):
        for k, v in data["event_sounds"].items():
            if k in merged_sounds:
                merged_sounds[k] = v
    result["event_sounds"] = merged_sounds

    return result


def _migrate(data: dict) -> dict:
    sv = data.get("schema_version", 0)
    if sv < 1:
        data["schema_version"] = 1
    return data
