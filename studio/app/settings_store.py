import json
from pathlib import Path
from typing import Any

class SettingsStore:
    def __init__(self, path: Path, defaults_path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.defaults_path = Path(defaults_path)
        self._data = {}
        self._load()

    def _load(self):
        # load defaults
        defaults = {}
        if self.defaults_path.exists():
            try:
                defaults = json.loads(self.defaults_path.read_text(encoding="utf-8"))
            except Exception:
                defaults = {}
        # load settings or create from defaults
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self._data = {}
        for k, v in defaults.items():
            self._data.setdefault(k, v)
        self._save()

    def _save(self):
        self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    def get(self, key: str, default: Any=None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any):
        self._data[key] = value
        self._save()
