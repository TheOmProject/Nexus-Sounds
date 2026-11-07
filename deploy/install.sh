#!/usr/bin/env bash
# Nexus Sounds public installer
# Usage: sudo bash public-install.sh [--yes] [--dry-run]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "${SCRIPT_DIR}")"

DRY_RUN=false
YES=false
for arg in "$@"; do
    case "${arg}" in
        --dry-run) DRY_RUN=true ;;
        --yes)     YES=true ;;
        *) echo "Unknown argument: ${arg}"; exit 1 ;;
    esac
done

# ── Root check ────────────────────────────────────────────────────────────────
if [[ "$(id -u)" -ne 0 ]]; then
    echo "ERROR: This installer must be run as root (sudo)."
    exit 1
fi

# ── Detect target user ────────────────────────────────────────────────────────
if [[ -n "${SUDO_USER:-}" ]]; then
    TARGET_USER="${SUDO_USER}"
else
    TARGET_USER="$(stat -c '%U' "${REPO_DIR}")"
fi

HOME_DIR="$(getent passwd "${TARGET_USER}" | cut -d: -f6)"
if [[ -z "${HOME_DIR}" ]]; then
    echo "ERROR: Cannot determine home directory for user '${TARGET_USER}'."
    exit 1
fi

INSTALL_DIR="${HOME_DIR}/nexus-sounds"

echo "=== Nexus Sounds Installer ==="
echo "Target user : ${TARGET_USER}"
echo "Home dir    : ${HOME_DIR}"
echo "Install dir : ${INSTALL_DIR}"
[[ "${DRY_RUN}" == true ]] && echo "(DRY RUN — no changes will be made)"
echo ""

# ── Architecture check ────────────────────────────────────────────────────────
ARCH="$(uname -m)"
if [[ "${ARCH}" != "aarch64" ]]; then
    echo "INSTALLATION BLOCKED: Unsupported architecture '${ARCH}'. aarch64 required."
    exit 1
fi

# ── OS check ─────────────────────────────────────────────────────────────────
if [[ -f /etc/os-release ]]; then
    # shellcheck disable=SC1091
    source /etc/os-release
    if [[ "${VERSION_ID:-}" != "12" ]]; then
        echo "WARNING: Unsupported OS version '${VERSION_ID:-unknown}'. Debian 12 recommended."
    fi
fi

# ── Python check ──────────────────────────────────────────────────────────────
if ! python3 --version &>/dev/null; then
    echo "INSTALLATION BLOCKED: python3 not found."
    exit 1
fi
PY_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
PY_MAJOR="${PY_VERSION%%.*}"
PY_MINOR="${PY_VERSION##*.}"
if [[ "${PY_MAJOR}" -lt 3 ]] || { [[ "${PY_MAJOR}" -eq 3 ]] && [[ "${PY_MINOR}" -lt 9 ]]; }; then
    echo "INSTALLATION BLOCKED: Python 3.9+ required, found ${PY_VERSION}."
    exit 1
fi

# ── aplay check ───────────────────────────────────────────────────────────────
if ! command -v aplay &>/dev/null; then
    echo "INSTALLATION BLOCKED: aplay not found. Install alsa-utils: sudo apt install alsa-utils"
    exit 1
fi

# ── websockets check ──────────────────────────────────────────────────────────
if ! python3 -c "import websockets" &>/dev/null; then
    echo "INSTALLATION BLOCKED: Python 'websockets' package not found."
    echo "Install with: sudo apt install python3-websockets  OR  pip3 install websockets"
    exit 1
fi

# ── rsync check ───────────────────────────────────────────────────────────────
if ! command -v rsync &>/dev/null; then
    echo "INSTALLATION BLOCKED: rsync not found. Install with: sudo apt install rsync"
    exit 1
fi

# ── klipper-audio coexistence warning ────────────────────────────────────────
# Detection uses only the service unit file — reliable when running as root
# (systemctl --user is unreliable in a root context without the target user's session).
if [[ -f "${HOME_DIR}/.config/systemd/user/klipper-audio.service" ]]; then
    echo "WARNING: klipper-audio.service was found on this system."
    echo "         Nexus Sounds will run alongside it (both connected to Moonraker)."
    echo "         You may want to disable klipper-audio.service manually after"
    echo "         verifying Nexus Sounds works correctly."
    echo "         This installer will NOT disable klipper-audio.service automatically."
    echo ""
fi

# ── Confirm ───────────────────────────────────────────────────────────────────
if [[ "${DRY_RUN}" == false && "${YES}" == false ]]; then
    read -r -p "Install Nexus Sounds to ${INSTALL_DIR}? [y/N] " reply
    if [[ "${reply}" != [yY] ]]; then
        echo "Aborted."
        exit 0
    fi
fi

if [[ "${DRY_RUN}" == true ]]; then
    echo "[DRY RUN] Would create install directory: ${INSTALL_DIR}"
    echo "[DRY RUN] Would copy repo files to: ${INSTALL_DIR}"
    echo "[DRY RUN] Would create config from: config.example.json"
    echo "[DRY RUN] Would install systemd user service: nexus-sounds.service"
    echo "[DRY RUN] Would enable and start: nexus-sounds.service (as ${TARGET_USER})"
    echo "[DRY RUN] Done — no changes made."
    exit 0
fi

# ── Backup existing config ────────────────────────────────────────────────────
if [[ -f "${INSTALL_DIR}/config.json" ]]; then
    BACKUP="${INSTALL_DIR}/config.json.bak.$(date +%Y%m%d-%H%M%S)"
    echo "Backing up existing config to ${BACKUP}"
    cp "${INSTALL_DIR}/config.json" "${BACKUP}"
fi

# ── Install files ─────────────────────────────────────────────────────────────
echo "Creating install directory: ${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}"
rsync -a --exclude='.git' --exclude='reference' --exclude='nexus-screen-dev' \
    --exclude='tests' --exclude='deploy' \
    "${REPO_DIR}/" "${INSTALL_DIR}/"

if [[ ! -f "${INSTALL_DIR}/config.json" ]]; then
    cp "${INSTALL_DIR}/config.example.json" "${INSTALL_DIR}/config.json"
    echo "Created default config.json"
fi
chown -R "${TARGET_USER}:${TARGET_USER}" "${INSTALL_DIR}"

# ── Install systemd service ───────────────────────────────────────────────────
SERVICE_DIR="${HOME_DIR}/.config/systemd/user"
mkdir -p "${SERVICE_DIR}"

TMPFILE="$(mktemp)"
trap 'rm -f "${TMPFILE}"' EXIT

sed \
    -e "s|@@INSTALL_DIR@@|${INSTALL_DIR}|g" \
    -e "s|@@HOME@@|${HOME_DIR}|g" \
    "${SCRIPT_DIR}/nexus-sounds.service.in" > "${TMPFILE}"

cp "${TMPFILE}" "${SERVICE_DIR}/nexus-sounds.service"
chown "${TARGET_USER}:${TARGET_USER}" "${SERVICE_DIR}/nexus-sounds.service"

echo "Reloading systemd daemon and enabling nexus-sounds.service"
sudo -u "${TARGET_USER}" XDG_RUNTIME_DIR="/run/user/$(id -u "${TARGET_USER}")" \
    systemctl --user daemon-reload
sudo -u "${TARGET_USER}" XDG_RUNTIME_DIR="/run/user/$(id -u "${TARGET_USER}")" \
    systemctl --user enable --now nexus-sounds.service

# ── Nexus Screen venv integration (optional) ─────────────────────────────────
# If Nexus Screen's venv exists, install a .pth file so nexus_sounds is
# importable from within it (required for the Settings → Sounds UI).
NS_VENV="${HOME_DIR}/nexus-screen-env"
if [[ -d "${NS_VENV}/lib" ]]; then
    PTH_DIR="$(find "${NS_VENV}/lib" -maxdepth 2 -name "site-packages" -type d | head -1)"
    if [[ -n "${PTH_DIR}" ]]; then
        PTH_FILE="${PTH_DIR}/nexus-sounds.pth"
        echo "${INSTALL_DIR}" > "${PTH_FILE}"
        chown "${TARGET_USER}:${TARGET_USER}" "${PTH_FILE}"
        echo "Installed .pth file: ${PTH_FILE}"
    fi
fi

echo ""
echo "=== Nexus Sounds installed successfully ==="
echo "Config : ${INSTALL_DIR}/config.json"
echo "Packs  : ${INSTALL_DIR}/packs/"
echo ""
echo "Check status with:"
echo "  systemctl --user status nexus-sounds"
echo "  journalctl --user -u nexus-sounds -b"
