import json
import threading
from pathlib import Path

import pytest
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from nexus_sounds.config import DEFAULT_CONFIG, load, merge_with_defaults, save, validate


def test_defaults(tmp_path):
    p = tmp_path / "config.json"
    result = load(p)
    assert result["schema_version"] == 1
    assert result["enabled"] is True
    assert result["volume"] == 70
    assert result["theme"] == "nexus_default"


def test_valid_config(tmp_path):
    p = tmp_path / "config.json"
    data = dict(DEFAULT_CONFIG)
    data["volume"] = 50
    p.write_text(json.dumps(data))
    result = load(p)
    assert result["volume"] == 50


def test_invalid_volume_clamped(tmp_path):
    p = tmp_path / "config.json"
    data = dict(DEFAULT_CONFIG)
    data["volume"] = 150
    result = validate(data)
    assert result["volume"] == 100


def test_invalid_type_raises():
    data = dict(DEFAULT_CONFIG)
    data["enabled"] = "yes"
    with pytest.raises(ValueError):
        validate(data)


def test_corrupt_json(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("not json")
    result = load(p)
    assert result == merge_with_defaults({})


def test_atomic_write(tmp_path):
    p = tmp_path / "config.json"
    save(p, DEFAULT_CONFIG)
    assert p.exists()
    loaded = json.loads(p.read_text())
    assert loaded["schema_version"] == 1


def test_atomic_write_concurrent(tmp_path):
    p = tmp_path / "config.json"
    errors = []

    def writer(vol):
        try:
            data = dict(DEFAULT_CONFIG)
            data["volume"] = vol
            save(p, data)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(v,)) for v in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    result = json.loads(p.read_text())
    assert isinstance(result["volume"], int)


def test_schema_migration(tmp_path):
    p = tmp_path / "config.json"
    data = dict(DEFAULT_CONFIG)
    data["schema_version"] = 0
    p.write_text(json.dumps(data))
    result = load(p)
    assert result["schema_version"] == 1


def test_missing_event_key(tmp_path):
    p = tmp_path / "config.json"
    data = dict(DEFAULT_CONFIG)
    events = dict(data["events"])
    del events["print_paused"]
    data["events"] = events
    p.write_text(json.dumps(data))
    result = load(p)
    assert "print_paused" in result["events"]


def test_path_traversal_theme():
    data = dict(DEFAULT_CONFIG)
    data["theme"] = "../etc/passwd"
    with pytest.raises(ValueError):
        validate(data)


def test_cooldown_clamped():
    data = dict(DEFAULT_CONFIG)
    data["cooldown_seconds"] = 999
    result = validate(data)
    assert result["cooldown_seconds"] == 30.0
