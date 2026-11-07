# Changelog

All notable changes to Nexus Sounds are documented here.

---

## [0.1.0-beta.1] — 2026-11-07

Initial public beta release.

### Added
- Moonraker WebSocket event daemon with reconnect logic
- USB ALSA playback via `aplay`
- Per-event sound assignments (`event_sounds` config dict)
- Individual event enable/disable
- Master enable/mute toggles
- Software volume control (0–100%)
- Sound preview via transient `_preview_request`/`_preview_file` config fields
- Cooldown timer (default 3 s) to prevent duplicate rapid-fire sounds
- Secure sound-pack discovery using `Path.relative_to()` traversal protection
- Atomic config writes with schema validation and schema versioning
- Independent user systemd service (`nexus-sounds.service`)
- Nexus Screen venv `.pth` integration
- `klipper-audio.service` coexistence warning in installer
- Settings bridge (`settings_bridge.py`) — Qt-free API for NS UI integration
- Nexus Screen UI: SoundsScreen, EventSoundsScreen, EventSoundScreen, SoundPacksScreen, PackSoundsScreen
- Built-in Nexus Default sound pack (4 WAV files)
- Moonraker Update Manager configuration
