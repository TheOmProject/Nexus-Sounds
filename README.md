# Nexus Sounds

> Audio notification add-on for [Nexus Screen](https://github.com/omarmunoz5371/Nexus-Screen).

Nexus Sounds is an **optional add-on** for Nexus Screen that plays short WAV notification sounds
for Klipper 3D printer events: startup, print start, print complete, print error, print cancelled,
print paused, and print resumed. It runs as an independent Python daemon that connects to Moonraker
via WebSocket and is configured through a new **Settings → Sounds** screen inside Nexus Screen.

Nexus Screen continues to function normally without Nexus Sounds installed.

**Status: Public Beta — v0.1.0-beta.1**  
See [Beta Limitations](#beta-limitations) before installing.

---

## Features

- **Seven printer events** — startup, print start, print complete, print error, print cancelled,
  print paused, print resumed
- **Per-event configuration** — assign a different sound file to each event, or disable individual
  events without affecting others
- **Master enable/disable** — globally turn off all sounds with one toggle
- **Mute control** — mute audio without changing any settings
- **Software volume** — 0–100% volume control applied at playback time
- **Sound preview** — preview any sound file from the touchscreen before applying it
- **Sound packs** — organized directories of WAV files; ships with the Nexus Default pack
- **USB audio** — plays through any ALSA-compatible USB audio device; no desktop environment required
- **Atomic configuration** — all settings written atomically via `os.replace()`; no corruption on
  unexpected shutdown
- **Secure pack discovery** — `Path.relative_to()` traversal protection prevents escaping the
  packs directory
- **Independent service** — user systemd service runs without sudo; no dependency on Nexus Screen
  or Nexus Video
- **Graceful degradation** — missing USB audio device produces a clear, nonfatal error; Nexus Screen
  UI degrades gracefully when Nexus Sounds is not installed

---

## Hardware Requirements

| Requirement | Minimum |
|---|---|
| **Nexus Screen** | v0.2.0-beta.6 or later |
| **SBC** | Raspberry Pi 4 or BigTreeTech CB1, 64-bit (aarch64) |
| **OS** | Debian 12 (Bookworm), 64-bit |
| **Python** | 3.9+ (Python 3.11 included with Bookworm) |
| **Audio** | USB audio device (class-compliant; tested with JMTek USB Sound Device) |
| **System packages** | `alsa-utils` (aplay), `python3-websockets`, `rsync` |
| **Free disk** | 50 MB |

---

## Installation

**Standalone — add to an existing Nexus Screen installation:**

```bash
git clone https://github.com/omarmunoz5371/Nexus-Sounds.git ~/nexus-sounds-src
sudo bash ~/nexus-sounds-src/deploy/install.sh
```

The installer:
1. Checks architecture, OS, Python, and required packages
2. Warns if `klipper-audio.service` is present — does **not** disable it automatically
3. Copies files to `~/nexus-sounds/`
4. Creates `~/nexus-sounds/config.json` from defaults (preserves existing config on update)
5. Installs and enables `nexus-sounds.service` as a user systemd service
6. Installs a `.pth` file into the Nexus Screen venv (if found) so the UI can import `nexus_sounds`

**Non-interactive:**

```bash
sudo bash ~/nexus-sounds-src/deploy/install.sh --yes
```

**Dry run (no changes):**

```bash
sudo bash ~/nexus-sounds-src/deploy/install.sh --dry-run
```

---

## Nexus Screen Integration

Nexus Screen v0.2.0-beta.6 and later include the **Settings → Sounds** screen.
When Nexus Sounds is not installed, the screen shows an installation notice rather than crashing.

The Settings → Sounds screen provides:
- **Master enable / Mute** toggles
- **Volume** control with live percentage display
- **Event Sounds** — browse all seven events, assign sound files, enable/disable per event
- **Sound Packs** — browse installed packs, preview sounds, set the active pack

No manual configuration is needed beyond running the installer.

---

## USB Audio Configuration

Nexus Sounds uses ALSA `aplay` for playback and auto-detects the first USB audio device.

To list available audio devices:

```bash
aplay -l
```

To verify which device Nexus Sounds is using:

```bash
journalctl --user -u nexus-sounds -b | grep "audio\|device\|card"
```

Volume is software-controlled (0–100%) inside Nexus Sounds and does not affect ALSA mixer levels.
If you want to adjust hardware volume separately:

```bash
# Example for USB audio on card 3
amixer -c 3 sset Speaker 80%
```

---

## Sound Event Assignments

Each of the seven events can have a sound file assigned from the active pack:

| Event key | Default sound | Description |
|---|---|---|
| `startup` | `startup.wav` | Nexus Screen has started |
| `print_start` | `print_start.wav` | A print job has begun |
| `print_complete` | `print_complete.wav` | Print finished successfully |
| `print_error` | `print_error.wav` | Print failed with an error |
| `print_cancelled` | *(none)* | Print was cancelled |
| `print_paused` | *(none)* | Print was paused |
| `print_resumed` | *(none)* | Print was resumed |

Assignments are stored in `~/nexus-sounds/config.json` under `event_sounds`.
You can also change them from the touchscreen at **Settings → Sounds → Event Sounds**.

---

## Sound Pack Structure

A sound pack is a directory containing WAV files and a `manifest.json`:

```
packs/
└── builtin/
│   └── nexus_default/
│       ├── manifest.json
│       ├── startup.wav
│       ├── print_start.wav
│       ├── print_complete.wav
│       └── print_error.wav
└── custom/           ← drop custom packs here
    └── my_pack/
        ├── manifest.json
        └── *.wav
```

**manifest.json format:**

```json
{
  "id": "my_pack",
  "name": "My Pack",
  "version": "1.0.0",
  "author": "Your Name",
  "description": "Description of the sounds",
  "sounds": {
    "startup": "startup.wav",
    "print_complete": "done.wav"
  }
}
```

Custom packs placed in `~/nexus-sounds/packs/custom/` are discovered automatically on daemon restart.

---

## Preview and Volume Controls

**Preview a sound** from the touchscreen at **Settings → Sounds → Event Sounds → [event] → Preview**.
The daemon plays the selected file once through the active audio device.

**Volume** (0–100%) is adjusted from the main Sounds screen and takes effect immediately on the
next played sound.

---

## Updating

### Via Moonraker Update Manager (recommended)

Add to `moonraker.conf`:

```ini
[update_manager nexus-sounds]
type: git_repo
path: ~/nexus-sounds
origin: https://github.com/omarmunoz5371/Nexus-Sounds.git
primary_branch: main
is_system_service: False
managed_services: nexus-sounds
```

See [`deploy/moonraker-update-manager.conf`](deploy/moonraker-update-manager.conf) for the
full snippet.

### Manual update

```bash
cd ~/nexus-sounds-src && git pull
sudo bash deploy/install.sh --yes
```

Your `config.json` and custom packs are preserved on every update.

---

## Troubleshooting

```bash
# Check service status
systemctl --user status nexus-sounds

# View recent logs
journalctl --user -u nexus-sounds -b --no-pager | tail -40

# Test audio manually
aplay -D plughw:CARD=Device,DEV=0 ~/nexus-sounds/packs/builtin/nexus_default/startup.wav
```

**Common issues:**

| Symptom | Cause | Fix |
|---|---|---|
| No sound | Audio device not found | Check `aplay -l`; verify card name |
| Service fails to start | Missing `websockets` | `sudo apt install python3-websockets` |
| "nexus_sounds not found" in NS | `.pth` not installed | Re-run installer; check NS venv path |
| Event sounds not playing | Event disabled in config | Enable from Settings → Sounds → Event Sounds |
| Preview has no effect | Daemon not running | `systemctl --user start nexus-sounds` |

Collect a bug report with:

```bash
bash ~/nexus-sounds-src/scripts/bug-report.sh "brief description"
```

---

## Uninstalling

```bash
sudo bash ~/nexus-sounds-src/deploy/uninstall.sh
```

This stops and removes the service. Config and packs are **preserved**.

To also delete `~/nexus-sounds/`:

```bash
sudo bash ~/nexus-sounds-src/deploy/uninstall.sh --purge
```

---

## Rollback

If a Nexus Sounds update causes problems, the previous service can be restored by rolling back
the git repository and re-running the installer:

```bash
cd ~/nexus-sounds-src
git log --oneline -5           # find the previous commit
git checkout <previous-commit>
sudo bash deploy/install.sh --yes
```

Your `config.json` is backed up automatically before each install to
`~/nexus-sounds/config.json.bak.<timestamp>`.

---

## Beta Limitations

This is a **public beta**. Known limitations in v0.1.0-beta.1:

- **Physically verified on one hardware configuration** — Voron Micron, Raspberry Pi 4,
  800×480 RGB565, Debian 12, JMTek USB audio device
- **Clean install not separately confirmed** — the full `git clone → install.sh → boot` sequence
  has not been run on a fresh machine; each component is verified on the production device
- **One built-in sound pack** — Nexus Default (4 sounds); custom packs are supported but no
  additional built-in packs ship in this release
- **aarch64 only** — installer blocks on other architectures (x86_64, armv7l)
- **No multi-printer support** — connects to a single Moonraker instance on `localhost:7125`
- **USB audio only** — built-in audio devices (3.5mm, HDMI) may work but are not tested

---

## Sound Pack Attribution

The included sound files (`packs/builtin/nexus_default/`) are original works created for
this project by the Nexus Sounds project. They are distributed under the same
[GNU General Public License v3.0](LICENSE) as the rest of this repository.

---

## Bug Reports

[Open a Bug Report](https://github.com/omarmunoz5371/Nexus-Sounds/issues/new)

Include the output of:

```bash
bash ~/nexus-sounds-src/scripts/bug-report.sh "brief description of the problem"
```

---

## License

Nexus Sounds is released under the [GNU General Public License v3.0](LICENSE).

---

## Related

- **[Nexus Screen](https://github.com/omarmunoz5371/Nexus-Screen)** — the touchscreen UI
  Nexus Sounds integrates with (required; install first)
- **[Nexus Video](https://github.com/omarmunoz5371/Nexus-Video)** — optional animated boot
  splash add-on (independent; not required)
