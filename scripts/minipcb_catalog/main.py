# minipcb_catalog/main.py
"""
Entry point for the miniPCB Catalog (website editor).

- Parses CLI flags (root, images-root, autosave, log level)
- Builds AppContext (paths, logger, bus)
- Loads/applies settings (SettingsService)
- Applies dark theme + dark Windows titlebar (best-effort)
- Creates and shows the MainWindow
"""

from __future__ import annotations

import sys
import argparse
from pathlib import Path
import logging

from PyQt5.QtCore import Qt, QCoreApplication
from PyQt5.QtWidgets import QApplication

from .app import build_default_context, AppContext
from .services.settings_service import SettingsService
from .utils.win_dark_titlebar import enable_dark_titlebar
from . import constants
from .ui.main_window import MainWindow  # type: ignore


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="minipcb-catalog", add_help=True)
    p.add_argument("--root", type=Path, default=Path.cwd(),
                   help="Project/site root containing your HTML pages (default: CWD).")
    p.add_argument("--images-root", type=Path, default=None,
                   help="Images folder (overrides settings.json and defaults).")
    p.add_argument("--autosave", type=int, default=None,
                   help=f"Autosave interval in seconds (default: {constants.DEFAULT_AUTOSAVE_SECONDS}).")
    p.add_argument("--log-level", type=str, default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                   help="Console log level.")
    return p.parse_args(argv)


def _apply_theme(app: QApplication, ctx: AppContext) -> None:
    """Apply Fusion + optional dark.qss theme if present."""
    app.setStyle("Fusion")
    qss_path = Path(__file__).resolve().parent / "theme" / "dark.qss"
    try:
        if qss_path.exists():
            app.setStyleSheet(qss_path.read_text(encoding="utf-8"))
            ctx.logger.info("Applied theme: %s", qss_path.name)
    except Exception as e:
        ctx.logger.warning("Failed to apply theme (%s): %s", qss_path, e)


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]

    # High-DPI friendliness
    try:
        QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    except Exception:
        pass

    args = _parse_args(argv)
    app = QApplication(sys.argv)

    # Build context and set log level
    ctx = build_default_context(args.root)
    ctx.logger.setLevel(getattr(logging, args.log_level))

    # Load & apply settings
    settings_svc = SettingsService(ctx)
    model = settings_svc.init_defaults()

    # CLI overrides (images root, autosave)
    if args.images_root is not None:
        model.images_root = str(args.images_root)
        settings_svc.save(model)  # reapplies to context

    autosave_s = args.autosave if args.autosave is not None else model.autosave_interval_s

    _apply_theme(app, ctx)

    # Create and show the main window
    win = MainWindow(ctx=ctx, autosave_seconds=autosave_s)
    win.show()

    # Best-effort dark titlebar on Windows (no-op elsewhere)
    enable_dark_titlebar(win)

    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
