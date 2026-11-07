"""Bash syntax and logic checks for the public installer."""
import subprocess
from pathlib import Path

INSTALLER = Path(__file__).parent.parent / "deploy" / "public-install.sh"
INSTALLER_TEXT = INSTALLER.read_text()


def test_installer_syntax():
    result = subprocess.run(["bash", "-n", str(INSTALLER)], capture_output=True, text=True)
    assert result.returncode == 0, f"Syntax error: {result.stderr}"


def test_no_eval_home():
    assert "eval echo" not in INSTALLER_TEXT


def test_uses_mktemp():
    assert "mktemp" in INSTALLER_TEXT


def test_root_check():
    # Installer uses $(id -u) rather than $EUID so it can be overridden in tests
    assert "id -u" in INSTALLER_TEXT


def test_detects_klipper_audio():
    assert "klipper-audio" in INSTALLER_TEXT


def test_no_systemctl_disable_klipper():
    import re
    assert not re.search(r"systemctl.*disable.*klipper-audio", INSTALLER_TEXT)


def test_dry_run_flag():
    assert "DRY_RUN" in INSTALLER_TEXT or "--dry-run" in INSTALLER_TEXT


def test_no_hardcoded_home():
    assert "/home/omar" not in INSTALLER_TEXT


def test_uses_getent():
    assert "getent passwd" in INSTALLER_TEXT


# ── D1 regression: rsync preflight ───────────────────────────────────────────

def test_rsync_preflight_present():
    """D1 fix: installer must check for rsync before using it."""
    assert "command -v rsync" in INSTALLER_TEXT


def test_rsync_blocked_message():
    assert "rsync not found" in INSTALLER_TEXT


def test_rsync_check_before_rsync_use():
    """rsync preflight must appear before the rsync -a call."""
    idx_check = INSTALLER_TEXT.find("command -v rsync")
    idx_use = INSTALLER_TEXT.find("rsync -a")
    assert idx_check != -1 and idx_use != -1
    assert idx_check < idx_use, "rsync preflight must precede rsync -a usage"


# ── D2 regression: service detection without root systemctl --user ────────────

def test_no_systemctl_user_for_klipper_detection():
    """D2 fix: klipper-audio detection must not use 'systemctl --user is-enabled'
    (unreliable when running as root without the user's D-Bus session)."""
    import re
    assert not re.search(r"systemctl\s+--user.*is-enabled\s+klipper-audio", INSTALLER_TEXT)


def test_uses_file_check_for_klipper_detection():
    """D2 fix: detection must rely on the service unit file path."""
    assert ".config/systemd/user/klipper-audio.service" in INSTALLER_TEXT


# ── Section 15 expanded installer safety checks ───────────────────────────────

def test_installer_has_config_backup_logic():
    """Installer must back up existing config.json before overwriting."""
    assert "config.json.bak" in INSTALLER_TEXT or "BACKUP" in INSTALLER_TEXT


def test_installer_checks_python():
    """Installer must verify python3 is available."""
    assert "python3" in INSTALLER_TEXT


def test_installer_checks_aplay():
    """Installer must verify aplay is available."""
    assert "aplay" in INSTALLER_TEXT


def test_installer_checks_websockets():
    """Installer must verify websockets Python package is importable."""
    assert "websockets" in INSTALLER_TEXT


def test_installer_creates_config_from_example():
    """Installer must create config.json from config.example.json if absent."""
    assert "config.example.json" in INSTALLER_TEXT


def test_installer_sets_ownership():
    """Installer must chown files to the target user, not root."""
    assert "chown" in INSTALLER_TEXT


def test_installer_arch_check():
    """Installer must block on non-aarch64 architecture."""
    assert "aarch64" in INSTALLER_TEXT


def test_installer_has_set_euo_pipefail():
    """Installer must use 'set -euo pipefail' for safe error handling."""
    assert "set -euo pipefail" in INSTALLER_TEXT


def test_installer_no_rm_rf():
    """Installer must not use 'rm -rf' (destructive without recovery path)."""
    import re
    assert not re.search(r"rm\s+-rf\s+\$\{?INSTALL_DIR", INSTALLER_TEXT), \
        "rm -rf on INSTALL_DIR found — use rsync --delete instead"


def test_installer_service_template_used():
    """Installer must generate service from .in template, not hardcode it."""
    assert "nexus-sounds.service.in" in INSTALLER_TEXT


def test_installer_klipper_audio_not_disabled():
    """Migration safety: installer must NOT disable klipper-audio.service."""
    import re
    assert not re.search(r"systemctl.*disable.*klipper-audio", INSTALLER_TEXT)
    assert not re.search(r"systemctl.*stop.*klipper-audio", INSTALLER_TEXT)
