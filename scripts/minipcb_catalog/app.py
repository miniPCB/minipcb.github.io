# minipcb_catalog/app.py
"""
Core application wiring for miniPCB Catalog (website editor).

- Bus: a tiny Qt signal hub shared across UI and services
- AppContext: typed container for roots/paths/logger/bus

This module has _no_ project-local imports so it can be used as the
first drop-in while the rest of the package is scaffolded.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import logging
from typing import Optional

from PyQt5.QtCore import QObject, pyqtSignal


class Bus(QObject):
    """
    Global event bus to avoid tight coupling between UI and services.

    Signals:
      - autosave_tick(int): seconds remaining until autosave.
      - document_dirty(bool): editor dirtiness changed.
      - page_loaded(str): absolute path of the newly loaded page.
      - status(str): short status line messages for the status bar.
      - long_task_started(str): identifier/label for a long task.
      - long_task_finished(str): identifier/label for a long task.
      - telemetry_event(dict): optional, lightweight analytics events.
    """
    autosave_tick = pyqtSignal(int)
    document_dirty = pyqtSignal(bool)
    page_loaded = pyqtSignal(str)
    status = pyqtSignal(str)
    long_task_started = pyqtSignal(str)
    long_task_finished = pyqtSignal(str)
    telemetry_event = pyqtSignal(dict)


@dataclass(slots=True)
class AppContext:
    """
    Shared, read-mostly application state.

    Attributes:
      root:           Project/site root (folder containing your HTML pages).
      settings_path:  JSON settings file path.
      images_root:    Default images folder (can be changed in Settings).
      analytics_dir:  Folder for telemetry storage (.minipcb/analytics).
      bus:            Global event bus instance.
      logger:         Preconfigured logger for the app.
    """
    root: Path
    settings_path: Path
    images_root: Path
    analytics_dir: Path
    bus: Bus
    logger: logging.Logger


def build_default_context(root: Optional[Path] = None) -> AppContext:
    """
    Build a usable AppContext with sensible defaults.

    - root defaults to current working directory.
    - settings.json lives at <root>/settings.json
    - images/ is the default images folder at <root>/images
    - analytics are stored under <root>/.minipcb/analytics
    - logger prints to console now; file handlers can be added later.
    """
    r = Path(root) if root else Path.cwd()
    settings_path = r / "settings.json"
    images_root = r / "images"
    analytics_dir = r / ".minipcb" / "analytics"
    _ensure_dir(images_root)
    _ensure_dir(analytics_dir)

    logger = _make_logger("minipcb_catalog")
    logger.debug("Initialized AppContext",
                 extra={"root": str(r),
                        "settings_path": str(settings_path),
                        "images_root": str(images_root),
                        "analytics_dir": str(analytics_dir)})

    return AppContext(
        root=r,
        settings_path=settings_path,
        images_root=images_root,
        analytics_dir=analytics_dir,
        bus=Bus(),
        logger=logger,
    )


# ---- internals -----------------------------------------------------------

def _ensure_dir(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        # We keep this defensive; callers can surface via status bar later.
        logging.getLogger("minipcb_catalog").warning(
            "Could not ensure directory %s: %s", path, e
        )


def _make_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        fmt = logging.Formatter("[%(levelname)s] %(message)s")
        ch.setFormatter(fmt)
        logger.addHandler(ch)
        # Avoid duplicate logs if parent handlers exist
        logger.propagate = False
    return logger


__all__ = ["Bus", "AppContext", "build_default_context"]
