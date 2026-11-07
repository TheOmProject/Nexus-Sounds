import logging
import os
import subprocess
from pathlib import Path
from typing import Optional
from uuid import uuid4

from . import __version__
from .config import DEFAULT_CONFIG, load, save, validate, merge_with_defaults
from .packs import discover_packs

logger = logging.getLogger(__name__)


def _get_install_dir() -> Optional[Path]:
    env_override = os.environ.get("NEXUS_SOUNDS_DIR")
    if env_override:
        p = Path(env_override)
        if p.is_dir():
            return p
    default = Path.home() / "nexus-sounds"
    if default.is_dir():
        return default
    return None


def _get_config_path() -> Optional[Path]:
    d = _get_install_dir()
    if d is None:
        return None
    return d / "config.json"


def is_installed() -> bool:
    return _get_install_dir() is not None


def get_status() -> dict:
    installed = is_installed()
    daemon_running = False
    if installed:
        try:
            result = subprocess.run(
                ["systemctl", "--user", "is-active", "nexus-sounds"],
                capture_output=True, text=True, timeout=3,
            )
            daemon_running = result.stdout.strip() == "active"
        except (OSError, subprocess.TimeoutExpired):
            pass
    d = _get_install_dir()
    return {
        "installed": installed,
        "daemon_running": daemon_running,
        "version": __version__,
        "install_dir": str(d) if d else "",
    }


def get_config() -> dict:
    p = _get_config_path()
    if p is None:
        return merge_with_defaults({})
    return load(p)


def _update_config(updates: dict) -> bool:
    p = _get_config_path()
    if p is None:
        return False
    try:
        data = load(p)
        data.update(updates)
        validated = validate(data)
        save(p, validated)
        return True
    except (ValueError, OSError) as e:
        logger.error("settings_bridge update failed: %s", e)
        return False


def set_enabled(enabled: bool) -> bool:
    if not is_installed():
        return False
    return _update_config({"enabled": enabled})


def set_muted(muted: bool) -> bool:
    if not is_installed():
        return False
    return _update_config({"muted": muted})


def set_volume(volume: int) -> bool:
    if not is_installed():
        return False
    volume = max(0, min(100, volume))
    return _update_config({"volume": volume})


def list_output_devices() -> list[dict]:
    if not is_installed():
        return []
    from .alsa import list_playback_devices
    current_cfg = get_config()
    current_device = current_cfg.get("output_device", "auto")
    result = [{"name": "auto", "description": "Auto-detect USB audio device", "is_active": current_device == "auto"}]
    for dev in list_playback_devices():
        result.append({
            "name": dev.short_name,
            "description": dev.description,
            "is_active": current_device == dev.short_name,
        })
    return result


def set_output_device(device: str) -> bool:
    if not is_installed():
        return False
    return _update_config({"output_device": device})


def list_packs() -> list[dict]:
    if not is_installed():
        return []
    d = _get_install_dir()
    if d is None:
        return []
    packs_dir = d / "packs"
    current_theme = get_config().get("theme", "nexus_default")
    result = []
    for pack in discover_packs(packs_dir):
        result.append({
            "id": pack.id,
            "name": pack.name,
            "description": pack.description,
            "is_active": pack.id == current_theme,
        })
    return result


def set_theme(theme_id: str) -> bool:
    if not is_installed():
        return False
    return _update_config({"theme": theme_id})


def set_event_enabled(event: str, enabled: bool) -> bool:
    if not is_installed():
        return False
    p = _get_config_path()
    if p is None:
        return False
    try:
        data = load(p)
        events = dict(data.get("events", {}))
        events[event] = enabled
        data["events"] = events
        validated = validate(data)
        save(p, validated)
        return True
    except (ValueError, OSError) as e:
        logger.error("set_event_enabled failed: %s", e)
        return False


def get_event_sounds() -> dict:
    """Return {event_key: filename_or_None} for all 7 events."""
    if not is_installed():
        return {}
    cfg = get_config()
    return dict(cfg.get("event_sounds", {}))


def set_event_sound(event: str, filename: Optional[str]) -> bool:
    """Assign a sound file to an event. None disables the event without deleting its slot."""
    if not is_installed():
        return False
    if filename is not None:
        if "/" in filename or "\\" in filename or ".." in filename:
            return False
    p = _get_config_path()
    if p is None:
        return False
    try:
        data = load(p)
        event_sounds = dict(data.get("event_sounds", {}))
        event_sounds[event] = filename
        data["event_sounds"] = event_sounds
        validated = validate(data)
        save(p, validated)
        return True
    except (ValueError, OSError) as e:
        logger.error("set_event_sound failed: %s", e)
        return False


def list_sounds_for_pack(pack_id: Optional[str] = None) -> list[dict]:
    """List available .wav files in the specified (or active) pack."""
    if not is_installed():
        return []
    d = _get_install_dir()
    if d is None:
        return []
    packs_dir = d / "packs"
    if pack_id is None:
        pack_id = get_config().get("theme", "nexus_default")
    for pack in discover_packs(packs_dir):
        if pack.id == pack_id:
            result = []
            for event_key, filename in pack.sounds.items():
                sound_path = pack.pack_dir / filename if filename else None
                result.append({
                    "filename": filename,
                    "event_key": event_key,
                    "path": str(sound_path) if sound_path else None,
                    "exists": bool(sound_path and sound_path.exists()),
                })
            return result
    return []


def preview_sound(event: str) -> bool:
    """Request daemon to play the sound currently assigned to `event`."""
    if not is_installed():
        return False
    p = _get_config_path()
    if p is None:
        return False
    try:
        data = load(p)
        data["_preview_request"] = event
        data["_preview_token"] = str(uuid4())
        save(p, data)
        return True
    except (ValueError, OSError) as e:
        logger.error("preview_sound failed: %s", e)
        return False


def preview_file(filename: str) -> bool:
    """Request daemon to play a specific sound file from the active pack."""
    if not is_installed():
        return False
    if not filename or "/" in filename or "\\" in filename or ".." in filename:
        return False
    p = _get_config_path()
    if p is None:
        return False
    try:
        data = load(p)
        data["_preview_file"] = filename
        data["_preview_token"] = str(uuid4())
        save(p, data)
        return True
    except (ValueError, OSError) as e:
        logger.error("preview_file failed: %s", e)
        return False
