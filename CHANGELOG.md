# Changelog

All notable changes to Nexus Sounds are documented here.

---

## [0.1.3] — 2026-11-15

### Fixed
- **print_error silent on G-code errors during printing**: Klipper logs
  `Unknown command:"HOME"` and similar errors as `notify_gcode_response`
  with a `!! ` prefix, without changing `print_stats.state`. The daemon
  now subscribes to `notify_gcode_response` and fires `print_error` when
  a `!! ` message arrives while `print_stats.state = "printing"`. Messages
  while idle (homing, calibration, terminal) are ignored to prevent false
  positives. The existing 3-second cooldown prevents duplicate sounds.

---

## [0.1.2] — 2026-11-15

### Fixed
- **print_start silent after error state**: `PrintStateTracker` only accepted
  `None/standby/paused` as valid prior states for the `printing` transition.
  If Klipper entered `error` before starting a print (e.g. a failed macro
  command during homing), the subsequent `error → printing` transition was
  silently ignored and no print_start sound fired. Fixed: any non-printing
  prior state now triggers `print_start`, except `paused → printing` which
  correctly triggers `print_resumed`.
- **State transitions now logged at INFO level** so print_stats changes are
  visible in `journalctl` for diagnosis.
- **Test false positive**: `test_no_hardcoded_resolution_overflow` now excludes
  1024 (a legitimate byte-unit constant) from the suspicious-pixel-value check.

---

## [0.1.1] — 2026-11-15

### Fixed
- **Print sounds silent**: `notify_status_update` params is a JSON list in the
  real Moonraker protocol (`params[0]` is the status dict), not a dict with a
  `"status"` key. The daemon was checking `isinstance(params, dict)` which
  evaluated False for every real notification, so print start and print complete
  events were never detected. Startup worked because it uses `notify_klippy_ready`
  (a different code path). Fixed to `params[0] if isinstance(params, list)`.
- **Mock Moonraker**: `emit_print_state` now sends the correct wire format
  (list) so integration tests exercise the same path as real Moonraker.
- **Update Manager INVALID**: `~/nexus-sounds` lacked a `.git` directory
  (rsync install). Initialized git repo, set `HEAD → main`, configured
  `origin` remote and `main` tracking branch, populated index with
  `skip-worktree` on locally modified files so `is_dirty` stays false.

### Tests
- Added 4 regression tests in `test_daemon.py`: list-format params fires event,
  old dict-format is handled gracefully, `print_complete` transition, no
  duplicate on reconnect.

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
