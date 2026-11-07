"""Security regression tests.

Covers confirmed findings from the Phase 3D security audit.
"""
import os
import tempfile
from pathlib import Path

import pytest

from nexus_sounds.packs import safe_path, load_manifest, discover_packs, _load_pack_from_dir


class TestSafePathSiblingDirectoryBug:
    """Regression test for the sibling-directory prefix collision bug.

    Previously: safe_path used str.startswith(pack_dir.resolve()) which allowed
    a path like /packs/ns_evil/x.wav to pass the check for pack_dir=/packs/ns
    because "ns_evil" string-starts-with "ns".

    Fix: use Path.relative_to() for exact directory containment.
    """

    def test_safe_path_sibling_directory_blocked(self, tmp_path):
        """A sibling directory with a name that is a prefix of pack_dir must be blocked."""
        pack_a = tmp_path / "ns"
        pack_b = tmp_path / "ns_evil"
        pack_a.mkdir()
        pack_b.mkdir()
        evil_file = pack_b / "secret.wav"
        evil_file.write_bytes(b"\x00" * 100)

        # Symlink inside pack_a pointing to the sibling directory's file
        symlink = pack_a / "x.wav"
        symlink.symlink_to(evil_file)

        with pytest.raises(ValueError, match="escapes pack directory"):
            safe_path(pack_a, "x.wav")

    def test_safe_path_symlink_to_etc_blocked(self, tmp_path):
        """Symlink pointing to /etc/passwd must be blocked."""
        pack_dir = tmp_path / "mypack"
        pack_dir.mkdir()
        sym = pack_dir / "startup.wav"
        sym.symlink_to("/etc/passwd")

        with pytest.raises(ValueError, match="escapes pack directory"):
            safe_path(pack_dir, "startup.wav")

    def test_safe_path_valid_file_still_works(self, tmp_path):
        """A real file inside the pack dir must still resolve correctly."""
        pack_dir = tmp_path / "mypack"
        pack_dir.mkdir()
        wav = pack_dir / "startup.wav"
        wav.write_bytes(b"\x00" * 100)

        result = safe_path(pack_dir, "startup.wav")
        assert result == wav.resolve()

    def test_safe_path_dotdot_blocked(self, tmp_path):
        pack_dir = tmp_path / "mypack"
        pack_dir.mkdir()
        with pytest.raises(ValueError, match="traversal"):
            safe_path(pack_dir, "../other.wav")

    def test_safe_path_absolute_blocked(self, tmp_path):
        pack_dir = tmp_path / "mypack"
        pack_dir.mkdir()
        with pytest.raises(ValueError, match="absolute"):
            safe_path(pack_dir, "/etc/passwd")

    def test_safe_path_subdirectory_blocked(self, tmp_path):
        pack_dir = tmp_path / "mypack"
        pack_dir.mkdir()
        with pytest.raises(ValueError, match="subdirectories"):
            safe_path(pack_dir, "subdir/startup.wav")

    def test_safe_path_empty_blocked(self, tmp_path):
        pack_dir = tmp_path / "mypack"
        pack_dir.mkdir()
        with pytest.raises(ValueError, match="empty"):
            safe_path(pack_dir, "")


class TestManifestSecurity:
    def test_malicious_description_treated_as_string(self, tmp_path):
        """Malicious content in manifest metadata is treated as plain string data."""
        pack_dir = tmp_path / "mypack"
        pack_dir.mkdir()
        manifest = {
            "id": "test",
            "name": "Test",
            "version": "1.0",
            "author": "$(rm -rf /)",
            "description": "<script>alert(1)</script>",
            "sounds": {"startup": "startup.wav"},
        }
        import json
        (pack_dir / "manifest.json").write_text(json.dumps(manifest))
        (pack_dir / "startup.wav").write_bytes(b"\x52\x49\x46\x46" + b"\x00" * 50)

        pack = _load_pack_from_dir(pack_dir)
        assert pack is not None
        # Description is stored as a plain string — not executed
        assert pack.description == "<script>alert(1)</script>"
        assert pack.author == "$(rm -rf /)"

    def test_sounds_injection_in_filename_blocked(self, tmp_path):
        """Shell injection in a sound filename is blocked by safe_path."""
        pack_dir = tmp_path / "mypack"
        pack_dir.mkdir()
        manifest = {
            "id": "test", "name": "Test", "version": "1.0",
            "author": "x", "description": "x",
            "sounds": {"startup": "$(rm -rf /).wav"},
        }
        import json
        (pack_dir / "manifest.json").write_text(json.dumps(manifest))

        pack = _load_pack_from_dir(pack_dir)
        assert pack is not None
        # Attempting to get the sound path must fail safely (contains /)
        from nexus_sounds.packs import get_sound_path
        result = get_sound_path(pack, "startup")
        assert result is None

    def test_missing_manifest_field_rejected(self, tmp_path):
        import json
        pack_dir = tmp_path / "p"
        pack_dir.mkdir()
        (pack_dir / "manifest.json").write_text(json.dumps({"id": "x", "name": "X"}))
        with pytest.raises(ValueError, match="missing required field"):
            load_manifest(pack_dir / "manifest.json")

    def test_sounds_not_dict_rejected(self, tmp_path):
        import json
        pack_dir = tmp_path / "p"
        pack_dir.mkdir()
        (pack_dir / "manifest.json").write_text(json.dumps({
            "id": "x", "name": "X", "version": "1", "author": "X",
            "description": "X", "sounds": ["startup.wav"],
        }))
        with pytest.raises(ValueError, match="dict"):
            load_manifest(pack_dir / "manifest.json")

    def test_corrupt_manifest_json_rejected(self, tmp_path):
        pack_dir = tmp_path / "p"
        pack_dir.mkdir()
        (pack_dir / "manifest.json").write_text("not valid { json }")
        with pytest.raises(ValueError, match="Cannot load manifest"):
            load_manifest(pack_dir / "manifest.json")


class TestConfigSecurity:
    def test_theme_path_traversal_rejected(self):
        from nexus_sounds.config import validate
        with pytest.raises(ValueError, match="invalid path"):
            validate({"schema_version": 1, "enabled": True, "volume": 70,
                      "muted": False, "theme": "../etc/shadow",
                      "output_device": "auto", "events": {}, "cooldown_seconds": 3.0})

    def test_theme_absolute_path_rejected(self):
        from nexus_sounds.config import validate
        with pytest.raises(ValueError, match="invalid path"):
            validate({"schema_version": 1, "enabled": True, "volume": 70,
                      "muted": False, "theme": "/etc/nexus",
                      "output_device": "auto", "events": {}, "cooldown_seconds": 3.0})

    def test_volume_out_of_range_clamped(self):
        from nexus_sounds.config import validate
        result = validate({"schema_version": 1, "enabled": True, "volume": 999,
                           "muted": False, "theme": "nexus_default",
                           "output_device": "auto", "events": {}, "cooldown_seconds": 3.0})
        assert result["volume"] == 100

    def test_enabled_non_bool_raises(self):
        from nexus_sounds.config import validate
        with pytest.raises(ValueError, match="bool"):
            validate({"schema_version": 1, "enabled": "yes", "volume": 70,
                      "muted": False, "theme": "nexus_default",
                      "output_device": "auto", "events": {}, "cooldown_seconds": 3.0})


class TestAlsaSubprocessSafety:
    def test_amixer_uses_list_not_shell(self):
        """Verify that alsa.py subprocess calls never use shell=True."""
        import inspect
        from nexus_sounds import alsa
        src = inspect.getsource(alsa)
        # Count occurrences of shell=True (should be zero)
        assert "shell=True" not in src

    def test_player_uses_list_not_shell(self):
        """Verify player.py subprocess calls never use shell=True."""
        import inspect
        from nexus_sounds import player
        src = inspect.getsource(player)
        assert "shell=True" not in src
