import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from nexus_sounds.alsa import (
    DeviceInfo,
    find_device_by_usb_id,
    get_mixer_controls,
    get_volume,
    has_volume_control,
    list_playback_devices,
    resolve_device,
    set_volume,
)

PROC_CARDS_CONTENT = """\
 0 [b1               ]: bcm2835_headpho - bcm2835 Headphones
                        bcm2835 Headphones
 3 [Device           ]: USB-Audio - USB PnP Audio Device
                        JMTek LLC. USB PnP Audio Device at usb-0000:01:00.0-1.3, full speed
"""


def test_list_devices_parses_proc(tmp_path):
    cards_file = tmp_path / "cards"
    cards_file.write_text(PROC_CARDS_CONTENT)
    with patch("nexus_sounds.alsa.Path") as MockPath:
        def path_side_effect(arg):
            if arg == "/proc/asound/cards":
                return cards_file
            return Path(arg)
        MockPath.side_effect = path_side_effect
        # test via real file read
    # Direct test with actual file patching
    with patch("nexus_sounds.alsa.Path") as MockPath:
        mock_cards = MagicMock()
        mock_cards.exists.return_value = True
        mock_cards.read_text.return_value = PROC_CARDS_CONTENT
        mock_usbid = MagicMock()
        mock_usbid.exists.return_value = False
        MockPath.side_effect = lambda x: mock_cards if x == "/proc/asound/cards" else mock_usbid
        devs = list_playback_devices()
    assert len(devs) == 2
    assert devs[0].card == 0
    assert devs[1].card == 3
    assert devs[1].short_name == "Device"


def test_find_device_by_usb_id():
    with patch("nexus_sounds.alsa.list_playback_devices") as mock_list:
        dev = DeviceInfo(card=3, name="Device", short_name="Device",
                         usb_id="0c76:1203", description="USB PnP Audio")
        mock_list.return_value = [dev]
        result = find_device_by_usb_id("0c76:1203")
    assert result is not None
    assert result.card == 3


def test_find_device_missing():
    with patch("nexus_sounds.alsa.list_playback_devices") as mock_list:
        mock_list.return_value = []
        result = find_device_by_usb_id("0c76:1203")
    assert result is None


def test_resolve_device_auto():
    with patch("nexus_sounds.alsa.find_device_by_usb_id") as mock_find:
        dev = DeviceInfo(card=3, name="Device", short_name="Device",
                         usb_id="0c76:1203", description="")
        mock_find.return_value = dev
        result = resolve_device("auto")
    assert result == "plughw:CARD=Device,DEV=0"


def test_resolve_device_explicit():
    result = resolve_device("Device")
    assert result == "plughw:CARD=Device,DEV=0"


def test_get_volume_parses():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "  Mono: Playback 688 [68%] [on]\n"
    with patch("subprocess.run", return_value=mock_result):
        result = get_volume("Device")
    assert result == 68


def test_get_volume_no_control():
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    with patch("subprocess.run", return_value=mock_result):
        result = get_volume("Device")
    assert result is None


def test_set_volume_calls_amixer():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""
    with patch("subprocess.run", return_value=mock_result) as mock_run:
        set_volume("Device", 75)
    args = mock_run.call_args[0][0]
    assert "amixer" in args
    assert "75%" in args


def test_has_volume_control():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "numid=1,iface=MIXER,name='Speaker Playback Volume'\n"
    with patch("subprocess.run", return_value=mock_result):
        assert has_volume_control("Device") is True

    mock_result.stdout = "numid=1,iface=MIXER,name='PCM Playback Switch'\n"
    with patch("subprocess.run", return_value=mock_result):
        assert has_volume_control("Device") is False
