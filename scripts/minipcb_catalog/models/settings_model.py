# minipcb_catalog/models/settings_model.py
"""
Typed settings model for miniPCB Catalog.

- Stores user-configurable options with safe defaults
- Keeps path-like fields as strings for portability in JSON
- Validation is minimal here; richer checks live in SettingsService
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict


@dataclass(slots=True)
class SettingsModel:
    theme: str = "dark"
    autosave_interval_s: int = 60
    analytics_enabled: bool = True
    linkcheck_online: bool = False
    images_root: str = "images"            # relative to project root
    export_single_path: str = "minipcb_catalog_single.py"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SettingsModel":
        """
        Build a SettingsModel from a (possibly partial) dict.
        Unknown keys are ignored; missing keys fall back to defaults.
        """
        base = cls()  # defaults
        # Copy known fields only
        for field in ("theme", "autosave_interval_s", "analytics_enabled",
                      "linkcheck_online", "images_root", "export_single_path"):
            if field in data and data[field] is not None:
                setattr(base, field, data[field])
        # basic sanity
        if not isinstance(base.autosave_interval_s, int) or base.autosave_interval_s < 5:
            base.autosave_interval_s = 60
        if base.theme not in ("dark", "light"):
            base.theme = "dark"
        return base

    def to_dict(self) -> Dict[str, Any]:
        """JSON-serializable dictionary."""
        return asdict(self)
