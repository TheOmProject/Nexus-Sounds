import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

USB_AUDIO_ID = "0c76:1203"


@dataclass
class DeviceInfo:
    card: int
    name: str
    short_name: str
    usb_id: Optional[str]
    description: str


def list_playback_devices() -> list[DeviceInfo]:
    cards_path = Path("/proc/asound/cards")
    if not cards_path.exists():
        return []
    try:
        text = cards_path.read_text()
    except OSError:
        return []

    devices = []
    # Lines come in pairs: "  N [ShortName       ]: driver - Long Name"
    for line in text.splitlines():
        m = re.match(r"^\s*(\d+)\s+\[(\S+)\s*\]:\s+\S+\s+-\s+(.*)", line)
        if m:
            card_num = int(m.group(1))
            short_name = m.group(2).strip()
            description = m.group(3).strip()
            usb_id = _read_usb_id(card_num)
            devices.append(DeviceInfo(
                card=card_num,
                name=short_name,
                short_name=short_name,
                usb_id=usb_id,
                description=description,
            ))
    return devices


def _read_usb_id(card_num: int) -> Optional[str]:
    p = Path(f"/proc/asound/card{card_num}/usbid")
    if not p.exists():
        return None
    try:
        return p.read_text().strip()
    except OSError:
        return None


def find_device_by_usb_id(usb_id: str) -> Optional[DeviceInfo]:
    for dev in list_playback_devices():
        if dev.usb_id == usb_id:
            return dev
    return None


def resolve_device(output_device: str) -> str:
    if output_device == "auto":
        dev = find_device_by_usb_id(USB_AUDIO_ID)
        if dev:
            return f"plughw:CARD={dev.short_name},DEV=0"
        logger.warning("USB audio device %s not found, using default", USB_AUDIO_ID)
        return "default"
    return f"plughw:CARD={output_device},DEV=0"


def get_volume(card_name: str) -> Optional[int]:
    try:
        result = subprocess.run(
            ["amixer", "-c", card_name, "sget", "Speaker"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return None
        m = re.search(r"\[(\d+)%\]", result.stdout)
        if m:
            return int(m.group(1))
        return None
    except (OSError, subprocess.TimeoutExpired):
        return None


def set_volume(card_name: str, pct: int) -> None:
    pct = max(0, min(100, pct))
    try:
        result = subprocess.run(
            ["amixer", "-c", card_name, "sset", "Speaker", f"{pct}%"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            logger.warning("amixer set_volume failed: %s", result.stderr.strip())
        else:
            logger.debug("Volume set to %d%% on card %s", pct, card_name)
    except (OSError, subprocess.TimeoutExpired) as e:
        logger.error("set_volume error: %s", e)


def get_mixer_controls(card_name: str) -> list[str]:
    try:
        result = subprocess.run(
            ["amixer", "-c", card_name, "controls"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return []
        controls = []
        for line in result.stdout.splitlines():
            m = re.search(r"name='([^']+)'", line)
            if m:
                controls.append(m.group(1))
        return controls
    except (OSError, subprocess.TimeoutExpired):
        return []


def has_volume_control(card_name: str) -> bool:
    controls = get_mixer_controls(card_name)
    return any("Volume" in c or "volume" in c for c in controls)
