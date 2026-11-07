import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

BUILTIN_EVENTS = ["startup", "print_start", "print_complete", "print_error"]
_REQUIRED_MANIFEST_KEYS = ["id", "name", "version", "author", "description", "sounds"]


@dataclass
class PackInfo:
    id: str
    name: str
    version: str
    author: str
    description: str
    sounds: dict[str, str]
    pack_dir: Path


def safe_path(pack_dir: Path, filename: str) -> Path:
    if not filename:
        raise ValueError("filename must not be empty")
    if filename.startswith("/"):
        raise ValueError(f"absolute path not allowed: {filename!r}")
    if ".." in filename.split("/"):
        raise ValueError(f"path traversal not allowed: {filename!r}")
    if "/" in filename:
        raise ValueError(f"subdirectories not allowed: {filename!r}")
    resolved = (pack_dir / filename).resolve()
    # Use is_relative_to (Python 3.9+) for exact directory containment.
    # str.startswith() has a prefix-collision bug:
    #   pack_dir="/packs/ns" would match resolved="/packs/ns_evil/x.wav".
    try:
        resolved.relative_to(pack_dir.resolve())
    except ValueError:
        raise ValueError(f"path escapes pack directory: {filename!r}")
    return resolved


def load_manifest(manifest_path: Path) -> dict:
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"Cannot load manifest {manifest_path}: {e}") from e

    for key in _REQUIRED_MANIFEST_KEYS:
        if key not in data:
            raise ValueError(f"Manifest missing required field: {key!r}")
    if not isinstance(data["sounds"], dict):
        raise ValueError("Manifest 'sounds' must be a dict")
    return data


def validate_pack(pack: PackInfo) -> list[str]:
    missing = []
    for event_key, filename in pack.sounds.items():
        try:
            p = safe_path(pack.pack_dir, filename)
            if not p.exists():
                missing.append(event_key)
        except ValueError:
            missing.append(event_key)
    return missing


def _load_pack_from_dir(pack_dir: Path) -> Optional[PackInfo]:
    manifest_path = pack_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        data = load_manifest(manifest_path)
        return PackInfo(
            id=data["id"],
            name=data["name"],
            version=data["version"],
            author=data["author"],
            description=data["description"],
            sounds=data["sounds"],
            pack_dir=pack_dir,
        )
    except ValueError as e:
        logger.warning("Skipping pack at %s: %s", pack_dir, e)
        return None


def discover_packs(base_dir: Path) -> list[PackInfo]:
    packs = []
    for subdir in ("builtin", "custom"):
        d = base_dir / subdir
        if not d.is_dir():
            continue
        for pack_dir in sorted(d.iterdir()):
            if not pack_dir.is_dir():
                continue
            pack = _load_pack_from_dir(pack_dir)
            if pack:
                packs.append(pack)
    return packs


def get_pack(packs: list[PackInfo], pack_id: str) -> Optional[PackInfo]:
    for p in packs:
        if p.id == pack_id:
            return p
    return None


def get_sound_path(pack: PackInfo, event_key: str) -> Optional[Path]:
    filename = pack.sounds.get(event_key)
    if not filename:
        return None
    try:
        p = safe_path(pack.pack_dir, filename)
        return p if p.exists() else None
    except ValueError:
        return None
