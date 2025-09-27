from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from .settings_store import SettingsStore
from .ai_usage_logger import AIUsageLogger

@dataclass
class AppContext:
    project_root: Path
    settings: SettingsStore = field(init=False)
    ai_logger: AIUsageLogger = field(init=False)

    def __post_init__(self):
        self.settings = SettingsStore(self.project_root / "config" / "settings.json",
                                      defaults_path=self.project_root / "config" / "defaults.json")
        self.ai_logger = AIUsageLogger(self.project_root / ".minipcb_ai" / "ai_usage.jsonl")

    # convenience getters
    @property
    def templates_dir(self) -> Path:
        return Path(self.settings.get("templates_dir"))

    @property
    def images_dir(self) -> Path:
        return Path(self.settings.get("images_dir"))
