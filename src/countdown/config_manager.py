import json
from pathlib import Path

class ConfigManager:
    def __init__(self):
        self.config_path = Path("config.json")
        self._last_mtime: float = 0.0

    def has_changed(self) -> bool:
        """Check if the config file has been modified on disk."""
        try:
            current_mtime = self.config_path.stat().st_mtime
            return current_mtime > self._last_mtime
        except OSError:
            return False

    def load_config(self) -> dict[str, object]:
        current_mtime = self.config_path.stat().st_mtime
        config = json.loads(self.config_path.read_text())
        self._last_mtime = current_mtime
        return config

    def save_config(self, new_config: dict[str, object]):
        self.config_path.write_text(json.dumps(new_config, indent=4))

config_manager = ConfigManager()