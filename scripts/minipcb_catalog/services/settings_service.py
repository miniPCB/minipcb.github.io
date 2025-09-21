# minipcb_catalog/services/settings_service.py
"""
SettingsService — load/save app settings for miniPCB Catalog.

Responsibilities:
- Read settings.json (if missing, create it from defaults)
- Validate & merge with defaults (unknown keys ignored)
- One-time .bak creation for the first overwrite
- Apply settings to the running AppContext (paths, intervals, toggles)

Notes:
- Secrets (API keys) are NOT stored here—read them from environment in ai_service.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
import json

from ..app import AppContext
from .. import constants
from ..models.settings_model import SettingsModel


class SettingsService:
    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self.settings_path: Path = ctx.settings_path
        self._bak_written = False  # track within process; we only create a .bak once per run

    # ---- Public API ------------------------------------------------------

    def init_defaults(self) -> SettingsModel:
        """
        Ensure settings.json exists; if not, create with DEFAULT_SETTINGS.
        Load the file, merge, apply to context, and return the model.
        """
        if not self.settings_path.exists():
            self.ctx.logger.info("Creating default settings at %s", self.settings_path)
            self._write_json(self.settings_path, constants.DEFAULT_SETTINGS)
        model = self.load()
        self.apply_to_context(model)
        return model

    def load(self) -> SettingsModel:
        """
        Load settings.json → SettingsModel (merged with defaults).
        """
        try:
            raw = self._read_json(self.settings_path)
        except Exception as e:
            self.ctx.logger.warning("Failed to read settings (%s). Using defaults. Error: %s",
                                    self.settings_path, e)
            raw = {}

        # Merge with defaults (shallow)
        merged = dict(constants.DEFAULT_SETTINGS)
        merged.update(raw or {})
        model = SettingsModel.from_dict(merged)
        return model

    def save(self, model: SettingsModel) -> None:
        """
        Persist SettingsModel to settings.json. Creates a one-time .bak before first overwrite.
        """
        try:
            if self.settings_path.exists() and not self._bak_written:
                bak = self.settings_path.with_suffix(self.settings_path.suffix + ".bak")
                bak.write_text(self.settings_path.read_text(encoding="utf-8"), encoding="utf-8")
                self._bak_written = True
        except Exception as e:
            self.ctx.logger.debug("Could not create settings backup: %s", e)

        data = model.to_dict()
        self._write_json(self.settings_path, data)
        # Re-apply to context after save (in case paths changed)
        self.apply_to_context(model)

    def apply_to_context(self, model: SettingsModel) -> None:
        """
        Apply relevant settings to the running AppContext.
        - images_root is stored as a string (relative or absolute); resolve under project root.
        - autosave interval & analytics toggles are consumed by UI/services later.
        """
        # images_root: allow absolute or relative to project root
        img = Path(model.images_root)
        if not img.is_absolute():
            img = (self.ctx.root / img).resolve()
        self.ctx.images_root = img
        self.ctx.analytics_dir.mkdir(parents=True, exist_ok=True)  # ensure analytics root exists
        img.mkdir(parents=True, exist_ok=True)

        # status message
        self.ctx.bus.status.emit(f"Settings applied • images: {img}")

    # ---- Internals -------------------------------------------------------

    def _read_json(self, path: Path) -> dict:
        text = path.read_text(encoding="utf-8")
        return json.loads(text)

    def _write_json(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(data, indent=2, ensure_ascii=False)
        path.write_text(text, encoding="utf-8")
