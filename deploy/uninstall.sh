#!/usr/bin/env bash
# Nexus Sounds uninstaller
# Usage: sudo bash uninstall.sh [--purge]
#   --purge  also removes ~/nexus-sounds/ (config and packs are deleted)
set -euo pipefail

PURGE=false
for arg in "$@"; do
    case "${arg}" in
        --purge) PURGE=true ;;
        *) echo "Unknown argument: ${arg}"; exit 1 ;;
    esac
done

if [[ "$(id -u)" -ne 0 ]]; then
    echo "ERROR: This installer must be run as root (sudo)."
    exit 1
fi

if [[ -n "${SUDO_USER:-}" ]]; then
    TARGET_USER="${SUDO_USER}"
else
    echo "ERROR: Could not determine target user. Run with sudo."
    exit 1
fi

HOME_DIR="$(getent passwd "${TARGET_USER}" | cut -d: -f6)"
INSTALL_DIR="${HOME_DIR}/nexus-sounds"
SERVICE_FILE="${HOME_DIR}/.config/systemd/user/nexus-sounds.service"

echo "=== Nexus Sounds Uninstaller ==="
echo "Target user : ${TARGET_USER}"

# Stop and disable service
if [[ -f "${SERVICE_FILE}" ]]; then
    echo "Stopping nexus-sounds.service..."
    sudo -u "${TARGET_USER}" XDG_RUNTIME_DIR="/run/user/$(id -u "${TARGET_USER}")" \
        systemctl --user stop nexus-sounds.service 2>/dev/null || true
    sudo -u "${TARGET_USER}" XDG_RUNTIME_DIR="/run/user/$(id -u "${TARGET_USER}")" \
        systemctl --user disable nexus-sounds.service 2>/dev/null || true
    rm -f "${SERVICE_FILE}"
    sudo -u "${TARGET_USER}" XDG_RUNTIME_DIR="/run/user/$(id -u "${TARGET_USER}")" \
        systemctl --user daemon-reload
    echo "Service removed."
fi

# Remove .pth from Nexus Screen venv
NS_VENV="${HOME_DIR}/nexus-screen-env"
if [[ -d "${NS_VENV}/lib" ]]; then
    PTH_FILE="$(find "${NS_VENV}/lib" -name "nexus-sounds.pth" 2>/dev/null | head -1)"
    if [[ -n "${PTH_FILE}" ]]; then
        rm -f "${PTH_FILE}"
        echo "Removed .pth file: ${PTH_FILE}"
    fi
fi

if [[ "${PURGE}" == true ]]; then
    if [[ -d "${INSTALL_DIR}" ]]; then
        echo "Removing installation directory: ${INSTALL_DIR}"
        rm -rf "${INSTALL_DIR}"
        echo "Removed."
    fi
else
    echo ""
    echo "Installation directory preserved: ${INSTALL_DIR}"
    echo "Your config.json and packs are intact."
    echo "To delete them permanently, re-run with --purge."
fi

echo ""
echo "=== Nexus Sounds uninstalled ==="
