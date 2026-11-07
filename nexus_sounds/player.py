import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class Player:
    def __init__(self) -> None:
        self._process: Optional[subprocess.Popen] = None

    def play(self, path: Path, device: str) -> bool:
        if not path.exists():
            logger.error("Sound file not found: %s", path)
            return False
        self.stop()
        try:
            self._process = subprocess.Popen(
                ["aplay", "-D", device, str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except FileNotFoundError:
            logger.error("aplay not found — cannot play sound")
            return False
        except OSError as e:
            logger.error("Player.play error: %s", e)
            return False

    def stop(self) -> None:
        if self._process is not None:
            try:
                self._process.terminate()
            except OSError:
                pass
            self._process = None

    def is_playing(self) -> bool:
        if self._process is None:
            return False
        return self._process.poll() is None

    @staticmethod
    def validate_sound_file(path: Path) -> bool:
        if not path.exists():
            return False
        if path.suffix.lower() != ".wav":
            return False
        try:
            return path.stat().st_size > 44
        except OSError:
            return False
