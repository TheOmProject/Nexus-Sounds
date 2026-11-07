"""Installer simulation framework.

Runs public-install.sh inside a fake filesystem root using temporary directories.
Mocks: systemctl, amixer, aplay, rsync (optionally absent), getent.
Never invokes the real installer against the actual machine.
"""
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _write_mock(bin_dir: Path, name: str, body: str) -> None:
    p = bin_dir / name
    p.write_text(f"#!/bin/sh\n{body}\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def build_fake_env(
    tmp_root: Path,
    target_user: str = "testuser",
    has_rsync: bool = True,
    has_aplay: bool = True,
    has_websockets: bool = True,
    arch: str = "aarch64",
    os_version: str = "12",
    existing_klipper_audio: bool = False,
    existing_ns_install: bool = False,
) -> dict:
    """Build a disposable fake filesystem environment and return env vars."""
    # Directories
    home_dir = tmp_root / "home" / target_user
    install_dir = home_dir / "nexus-sounds"
    bin_dir = tmp_root / "usr" / "local" / "bin"
    etc_dir = tmp_root / "etc"
    service_dir = home_dir / ".config" / "systemd" / "user"
    for d in (home_dir, bin_dir, etc_dir, service_dir):
        d.mkdir(parents=True, exist_ok=True)

    # /etc/os-release
    (etc_dir / "os-release").write_text(
        f'ID=debian\nVERSION_ID="{os_version}"\nNAME="Debian GNU/Linux"\n'
    )

    # Mock binaries
    _write_mock(bin_dir, "systemctl", 'echo "systemctl: $@" >&2; exit 0')
    _write_mock(bin_dir, "amixer", 'echo "amixer: $@" >&2; exit 0')
    _write_mock(bin_dir, "id", f'case "$1" in -u) echo 0;; *) echo {target_user};; esac')
    _write_mock(bin_dir, "uname", f'case "$1" in -m) echo "{arch}";; *) echo Linux;; esac')
    _write_mock(bin_dir, "getent",
                f'echo "{target_user}:x:1000:1000:Test User:{home_dir}:/bin/sh"')

    if has_rsync:
        _write_mock(bin_dir, "rsync", 'echo "rsync: $@" >&2; exit 0')

    if has_aplay:
        _write_mock(bin_dir, "aplay", 'echo "aplay: $@" >&2; exit 0')

    # Mock python3 that accepts -c "import websockets" etc.
    py_body = (
        'case "$*" in\n'
        '  *"import websockets"*) ' + ("exit 0" if has_websockets else "exit 1") + " ;;\n"
        '  *) /usr/bin/python3 "$@" ;;\n'
        'esac'
    )
    _write_mock(bin_dir, "python3", py_body)

    # Mock sudo -u <user> ...
    _write_mock(bin_dir, "sudo", 'shift; shift; exec "$@"')

    # Proxy mocks for core system utilities — keep bin_dir self-contained so the
    # test PATH can be bin_dir-only, ensuring absent deps (no aplay/rsync mock)
    # are truly invisible to `command -v`.
    for util, real in [
        ("cut", "/usr/bin/cut"),
        ("cp", "/usr/bin/cp"),
        ("mkdir", "/usr/bin/mkdir"),
        ("mktemp", "/usr/bin/mktemp"),
        ("sed", "/usr/bin/sed"),
        ("rm", "/usr/bin/rm"),
        ("date", "/usr/bin/date"),
        ("stat", "/usr/bin/stat"),
        ("chown", "/usr/bin/chown"),
        ("dirname", "/usr/bin/dirname"),
        ("basename", "/usr/bin/basename"),
        ("bash", "/usr/bin/bash"),
        ("sh", "/usr/bin/sh"),
        ("tee", "/usr/bin/tee"),
        ("sort", "/usr/bin/sort"),
        ("tr", "/usr/bin/tr"),
    ]:
        _write_mock(bin_dir, util, f'exec {real} "$@"')

    if existing_klipper_audio:
        (service_dir / "klipper-audio.service").write_text("[Unit]\nDescription=mock\n")

    if existing_ns_install:
        install_dir.mkdir(parents=True, exist_ok=True)
        (install_dir / "config.json").write_text('{"schema_version": 1, "volume": 55}\n')

    env = {
        **os.environ,
        "HOME": str(home_dir),
        "SUDO_USER": target_user,
        "EUID": "0",
        "PATH": str(bin_dir),
        "INSTALL_DIR": str(install_dir),
    }
    return env, home_dir, install_dir, service_dir


def run_installer(
    extra_args: list[str],
    env: dict,
    timeout: int = 30,
) -> subprocess.CompletedProcess:
    """Run the installer with fake env. Skips the EUID check by injecting EUID=0."""
    installer_path = REPO_ROOT / "deploy" / "public-install.sh"
    # Patch a copy of the installer to skip the EUID check (since we can't actually be root)
    # and to use the mocked binaries.
    cmd = ["bash", str(installer_path)] + extra_args
    return subprocess.run(
        cmd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
