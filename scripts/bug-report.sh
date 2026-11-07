#!/usr/bin/env bash
# Nexus Sounds bug report collector
# Usage: bash bug-report.sh "brief description of the problem"
set -euo pipefail

DESCRIPTION="${1:-no description provided}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
REPORT_FILE="${HOME}/nexus-sounds-bug-report-${TIMESTAMP}.txt"

{
    echo "=== Nexus Sounds Bug Report ==="
    echo "Generated : $(date)"
    echo "Description: ${DESCRIPTION}"
    echo ""
    echo "--- Service Status ---"
    systemctl --user status nexus-sounds.service --no-pager 2>&1 || echo "(service not found)"
    echo ""
    echo "--- Recent Logs ---"
    journalctl --user -u nexus-sounds -b --no-pager -n 50 2>&1 || echo "(no logs)"
    echo ""
    echo "--- Config (sanitized) ---"
    CONFIG_FILE="${HOME}/nexus-sounds/config.json"
    if [[ -f "${CONFIG_FILE}" ]]; then
        python3 -c "
import json, sys
try:
    with open('${CONFIG_FILE}') as f:
        d = json.load(f)
    # Remove any transient/sensitive keys
    for k in ['_preview_request','_preview_file','_preview_token']:
        d.pop(k, None)
    print(json.dumps(d, indent=2))
except Exception as e:
    print(f'Error reading config: {e}')
"
    else
        echo "(config.json not found at ${CONFIG_FILE})"
    fi
    echo ""
    echo "--- Audio Devices ---"
    aplay -l 2>&1 || echo "(aplay not available)"
    echo ""
    echo "--- Python Version ---"
    python3 --version 2>&1
    echo ""
    echo "--- Package Version ---"
    python3 -c "import nexus_sounds; print(getattr(nexus_sounds, '__version__', 'unknown'))" 2>&1 || echo "(nexus_sounds not importable)"
    echo ""
    echo "--- OS ---"
    uname -a
    cat /etc/os-release 2>/dev/null || true
} > "${REPORT_FILE}"

echo "Bug report saved to: ${REPORT_FILE}"
echo "Attach this file when opening an issue at:"
echo "  https://github.com/omarmunoz5371/Nexus-Sounds/issues/new"
