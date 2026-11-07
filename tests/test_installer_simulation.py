"""Installer simulation tests.

All tests run in temporary directories. No real installation is performed.
The installer cannot be run as EUID=0 in a test context, so tests that
require root-only paths are validated by static inspection or mock.
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from tests.installer_simulation.sim import build_fake_env, run_installer, REPO_ROOT

INSTALLER = REPO_ROOT / "deploy" / "public-install.sh"


# ── static syntax check ───────────────────────────────────────────────────────

def test_installer_syntax():
    r = subprocess.run(["bash", "-n", str(INSTALLER)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ── dry-run simulation ────────────────────────────────────────────────────────

class TestDryRun:
    def test_dry_run_no_writes(self, tmp_path):
        env, home_dir, install_dir, _ = build_fake_env(tmp_path)
        r = run_installer(["--dry-run", "--yes"], env)
        assert "[DRY RUN]" in r.stdout
        assert "Done" in r.stdout or "no changes" in r.stdout.lower()
        assert not install_dir.exists(), "dry-run must not create install dir"

    def test_dry_run_prints_would_create(self, tmp_path):
        env, home_dir, install_dir, _ = build_fake_env(tmp_path)
        r = run_installer(["--dry-run", "--yes"], env)
        assert "Would create install directory" in r.stdout

    def test_dry_run_blocked_arch(self, tmp_path):
        env, home_dir, install_dir, _ = build_fake_env(tmp_path, arch="x86_64")
        r = run_installer(["--dry-run", "--yes"], env)
        assert "INSTALLATION BLOCKED" in r.stdout
        assert r.returncode != 0


# ── preflight checks ──────────────────────────────────────────────────────────

class TestPreflightChecks:
    def test_missing_rsync_blocked(self, tmp_path):
        env, _, _, _ = build_fake_env(tmp_path, has_rsync=False)
        r = run_installer(["--dry-run", "--yes"], env)
        assert "rsync" in r.stdout.lower()
        assert r.returncode != 0

    def test_missing_aplay_blocked(self, tmp_path):
        env, _, _, _ = build_fake_env(tmp_path, has_aplay=False)
        r = run_installer(["--dry-run", "--yes"], env)
        assert "aplay" in r.stdout.lower()
        assert r.returncode != 0

    def test_missing_websockets_blocked(self, tmp_path):
        env, _, _, _ = build_fake_env(tmp_path, has_websockets=False)
        r = run_installer(["--dry-run", "--yes"], env)
        assert "websockets" in r.stdout.lower()
        assert r.returncode != 0

    def test_unsupported_arch_blocked(self, tmp_path):
        env, _, _, _ = build_fake_env(tmp_path, arch="armv7l")
        r = run_installer(["--dry-run", "--yes"], env)
        assert "INSTALLATION BLOCKED" in r.stdout
        assert r.returncode != 0

    def test_all_deps_present_pass(self, tmp_path):
        env, _, _, _ = build_fake_env(tmp_path)
        r = run_installer(["--dry-run", "--yes"], env)
        assert r.returncode == 0, r.stdout + r.stderr


# ── klipper-audio coexistence ─────────────────────────────────────────────────

class TestKlipperAudioCoexistence:
    def test_klipper_audio_warning_shown(self, tmp_path):
        env, _, _, _ = build_fake_env(tmp_path, existing_klipper_audio=True)
        r = run_installer(["--dry-run", "--yes"], env)
        assert "klipper-audio" in r.stdout

    def test_klipper_audio_not_disabled(self, tmp_path):
        env, _, _, svc_dir = build_fake_env(tmp_path, existing_klipper_audio=True)
        r = run_installer(["--dry-run", "--yes"], env)
        # installer must NEVER disable klipper-audio
        assert "disable" not in r.stdout or "klipper-audio" not in r.stdout.split("disable")[1][:100]
        # Service file must still exist
        assert (svc_dir / "klipper-audio.service").exists()

    def test_no_klipper_audio_no_warning(self, tmp_path):
        env, _, _, _ = build_fake_env(tmp_path, existing_klipper_audio=False)
        r = run_installer(["--dry-run", "--yes"], env)
        assert "klipper-audio" not in r.stdout


# ── upgrade (config preservation) ────────────────────────────────────────────

class TestUpgrade:
    def test_existing_config_preserved_in_dry_run(self, tmp_path):
        env, _, install_dir, _ = build_fake_env(tmp_path, existing_ns_install=True)
        original_config = (install_dir / "config.json").read_text()
        r = run_installer(["--dry-run", "--yes"], env)
        assert r.returncode == 0
        assert (install_dir / "config.json").read_text() == original_config, \
            "dry-run must not touch config.json"


# ── static installer property tests ──────────────────────────────────────────

class TestInstallerProperties:
    def _src(self):
        return INSTALLER.read_text()

    def test_set_euo_pipefail(self):
        assert "set -euo pipefail" in self._src()

    def test_no_eval_home(self):
        assert "eval echo" not in self._src()

    def test_uses_mktemp(self):
        assert "mktemp" in self._src()

    def test_uses_getent(self):
        assert "getent passwd" in self._src()

    def test_rsync_check_before_rsync_use(self):
        src = self._src()
        rsync_check_pos = src.find("command -v rsync")
        rsync_use_pos = src.find("rsync -a")
        assert rsync_check_pos != -1
        assert rsync_use_pos != -1
        assert rsync_check_pos < rsync_use_pos

    def test_no_systemctl_user_for_klipper_detection(self):
        src = self._src()
        # Should NOT have "systemctl --user is-enabled klipper-audio"
        assert "is-enabled klipper-audio" not in src

    def test_uses_file_check_for_klipper_detection(self):
        assert "klipper-audio.service" in self._src()

    def test_config_backup_logic(self):
        assert "config.json.bak" in self._src()

    def test_chown_target_user(self):
        assert "chown" in self._src()
        assert "TARGET_USER" in self._src()

    def test_no_hardcoded_home_omar(self):
        assert "/home/omar" not in self._src()

    def test_trap_cleanup(self):
        assert "trap" in self._src()


# ── migration sequence documentation test ────────────────────────────────────

class TestMigrationDocumentation:
    def test_migration_docs_exist(self):
        docs = REPO_ROOT / "docs" / "MIGRATION.md"
        assert docs.exists()
        content = docs.read_text()
        assert "klipper-audio" in content.lower()
        assert "nexus-sounds" in content.lower()

    def test_rollback_docs_exist(self):
        rollback = REPO_ROOT / "docs" / "ROLLBACK.md"
        assert rollback.exists()
