# Nexus Sounds — Release Notes

---

## v0.1.0-beta.1 — Public Beta

> Compatible with Nexus Screen v0.2.0-beta.6 or later.

### What is Nexus Sounds?

Nexus Sounds is an **optional audio notification add-on** for
[Nexus Screen](https://github.com/TheOmProject/Nexus-Screen).
It plays short WAV sounds for Klipper 3D printer events (startup, print start, print complete,
print error, print cancelled, print paused, print resumed) and is configured through a new
**Settings → Sounds** panel inside Nexus Screen.

Nexus Screen continues to function without Nexus Sounds installed.

---

### New in this release

**Audio daemon:**
- Moonraker WebSocket event listener with reconnect logic
- USB ALSA playback via `aplay` (class-compliant USB audio devices)
- Per-event sound assignments — each event maps to a specific WAV file
- Individual event enable/disable — silence one event without affecting others
- Master enable/mute — global on/off and mute toggles
- Software volume (0–100%) applied at playback time
- Sound preview — preview any file from the touchscreen without committing
- Cooldown timer (default 3 s) prevents rapid-fire duplicate sounds

**Sound packs:**
- Secure pack discovery using `Path.relative_to()` traversal protection
- Built-in Nexus Default pack: `startup.wav`, `print_start.wav`, `print_complete.wav`,
  `print_error.wav`
- Custom packs supported: drop into `~/nexus-sounds/packs/custom/<pack_id>/`

**Configuration:**
- JSON config at `~/nexus-sounds/config.json` with atomic writes (`os.replace()`)
- Schema versioning and validation
- `event_sounds` dict maps event keys to filenames; `None` entries disable the event's sound
- Existing config preserved on update (timestamped backup created automatically)

**Installer:**
- Architecture check (aarch64 required)
- Python 3.9+ check
- `klipper-audio.service` coexistence warning — installer does **not** disable existing audio daemons
- NS venv `.pth` integration for Nexus Screen UI

**Nexus Screen UI (requires Nexus Screen v0.2.0-beta.6):**
- Main Sounds screen: master enable/mute toggle cards, volume row, Event Sounds and Sound Packs navigation
- Event Sounds screen: seven-event scrollable list with icons, filenames, and chevrons
- Individual event selector: file browser, Enable toggle, Preview/Apply/Cancel
- Sound Packs browser: two-column layout, pack metadata, Browse Sounds, Set as Active

---

### Hardware verified

| Hardware | Audio | Status |
|---|---|---|
| Voron Micron, Raspberry Pi 4, 800×480 RGB565, Debian 12 | JMTek USB (0c76:1203, ALSA card 3) | **PHYSICALLY VERIFIED** — full service lifecycle, event sounds, preview, volume, UI |

**PHYSICALLY VERIFIED** = installed and confirmed working on real hardware with traceable evidence.

---

### Known limitations

- **Clean install not separately confirmed** — the full `git clone → install.sh → boot` sequence
  has not been run on a fresh machine; all components verified on the production Voron Micron
- **One built-in sound pack** — Nexus Default (4 sounds); custom packs supported but no additional
  packs ship with this release
- **aarch64 only** — installer blocks on other architectures
- **USB audio only** — built-in audio (3.5mm, HDMI) may work but is untested
- **No multi-printer support** — single Moonraker instance on `localhost:7125`

---

### Installation

```bash
git clone https://github.com/TheOmProject/Nexus-Sounds.git ~/nexus-sounds
sudo bash ~/nexus-sounds/deploy/install.sh
```

See [README.md](README.md) for full installation and configuration instructions.

---

### Minimum requirements

| Requirement | Minimum |
|---|---|
| Nexus Screen | v0.2.0-beta.6 or later |
| SBC | Raspberry Pi 4 or BigTreeTech CB1, 64-bit (aarch64) |
| OS | Debian 12 (Bookworm), 64-bit |
| Python | 3.9+ |
| System packages | `alsa-utils`, `python3-websockets`, `rsync` |
| Audio device | USB class-compliant audio device |
