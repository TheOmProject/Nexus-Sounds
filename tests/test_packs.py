import json
import struct
import wave
from pathlib import Path

import pytest
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from nexus_sounds.packs import (
    PackInfo,
    discover_packs,
    get_pack,
    get_sound_path,
    load_manifest,
    safe_path,
    validate_pack,
)


VALID_MANIFEST = {
    "id": "test_pack",
    "name": "Test Pack",
    "version": "1.0.0",
    "author": "Test",
    "description": "Test pack",
    "sounds": {
        "startup": "startup.wav",
        "print_start": "print_start.wav",
    },
}


def make_wav(path: Path) -> None:
    with wave.open(str(path), "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(44100)
        for _ in range(10):
            f.writeframes(struct.pack("<h", 0))


def test_load_valid_manifest(tmp_path):
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(VALID_MANIFEST))
    result = load_manifest(p)
    assert result["id"] == "test_pack"


def test_load_missing_field(tmp_path):
    p = tmp_path / "manifest.json"
    bad = dict(VALID_MANIFEST)
    del bad["id"]
    p.write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="id"):
        load_manifest(p)


def test_safe_path_valid(tmp_path):
    p = safe_path(tmp_path, "startup.wav")
    assert str(p).startswith(str(tmp_path))


def test_safe_path_traversal_dotdot(tmp_path):
    with pytest.raises(ValueError):
        safe_path(tmp_path, "../etc/passwd")


def test_safe_path_absolute(tmp_path):
    with pytest.raises(ValueError):
        safe_path(tmp_path, "/etc/passwd")


def test_safe_path_slash(tmp_path):
    with pytest.raises(ValueError):
        safe_path(tmp_path, "subdir/file.wav")


def test_discover_packs(tmp_path):
    builtin = tmp_path / "builtin" / "my_pack"
    builtin.mkdir(parents=True)
    (builtin / "manifest.json").write_text(json.dumps(VALID_MANIFEST))
    custom = tmp_path / "custom" / "another_pack"
    custom.mkdir(parents=True)
    manifest2 = dict(VALID_MANIFEST)
    manifest2["id"] = "another_pack"
    (custom / "manifest.json").write_text(json.dumps(manifest2))

    packs = discover_packs(tmp_path)
    ids = [p.id for p in packs]
    assert "test_pack" in ids
    assert "another_pack" in ids


def test_validate_pack_missing_file(tmp_path):
    pack = PackInfo(
        id="test", name="Test", version="1.0", author="A",
        description="D",
        sounds={"startup": "startup.wav"},
        pack_dir=tmp_path,
    )
    missing = validate_pack(pack)
    assert "startup" in missing


def test_get_sound_path_valid(tmp_path):
    make_wav(tmp_path / "startup.wav")
    pack = PackInfo(
        id="test", name="Test", version="1.0", author="A",
        description="D",
        sounds={"startup": "startup.wav"},
        pack_dir=tmp_path,
    )
    p = get_sound_path(pack, "startup")
    assert p is not None
    assert p.exists()


def test_get_sound_path_missing_event(tmp_path):
    pack = PackInfo(
        id="test", name="Test", version="1.0", author="A",
        description="D",
        sounds={"startup": "startup.wav"},
        pack_dir=tmp_path,
    )
    result = get_sound_path(pack, "print_paused")
    assert result is None
