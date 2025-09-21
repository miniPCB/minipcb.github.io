# minipcb_catalog/services/file_service.py
"""
FileService — safe disk I/O for miniPCB Catalog.

Goals:
- Atomic writes (temp -> fsync -> replace) to avoid partial/corrupt saves
- Optional single-backup policy (filename.ext.bak) with opt-in
- Simple read/rename helpers
- Minimal dependencies so it can be adopted early and wired into the UI later

Notes:
- On Windows, Path.replace() is atomic only on the same filesystem. We write
  the temp file to the same directory to preserve atomicity.
- We never store secrets or modify permissions.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import io
import os
import tempfile

from ..app import AppContext


@dataclass(slots=True)
class WriteOptions:
    """Options for write_text()."""
    make_backup: bool = False      # create/refresh a single .bak file before replacing
    delete_backup_after_verify: bool = False  # if True, remove .bak after successful write/verify
    encoding: str = "utf-8"
    newline: Optional[str] = None  # None = platform default; or "\n"


class FileService:
    def __init__(self, ctx: AppContext):
        self.ctx = ctx

    # ---- Public API ------------------------------------------------------

    def read_text(self, path: Path, encoding: str = "utf-8") -> str:
        """Read file text with explicit encoding."""
        return path.read_text(encoding=encoding)

    def write_text(self, path: Path, text: str, opts: Optional[WriteOptions] = None) -> None:
        """
        Safely write text to disk with atomic replace and optional single backup.

        Steps:
          1) (optional) write/refresh <file>.bak with current contents
          2) write to a temp file in the same directory
          3) fsync temp, then replace original
          4) (optional) verify and remove .bak if requested
        """
        opts = opts or WriteOptions()
        parent = path.parent
        parent.mkdir(parents=True, exist_ok=True)

        # 1) optional single backup
        if opts.make_backup and path.exists():
            bak = self._bak_path(path)
            try:
                bak.write_text(path.read_text(encoding=opts.encoding), encoding=opts.encoding)
            except Exception as e:
                self.ctx.logger.warning("Could not write backup %s: %s", bak, e)

        # 2) write temp in same folder
        tmp_path = self._write_temp(parent, text, opts.encoding, opts.newline)

        # 3) fsync & atomic replace
        self._atomic_replace(tmp_path, path)

        # 4) optional post-verify cleanup
        if opts.make_backup and opts.delete_backup_after_verify:
            bak = self._bak_path(path)
            try:
                # minimal verification: file exists and non-empty if text is non-empty
                if path.exists() and ((not text) or path.stat().st_size > 0):
                    bak.unlink(missing_ok=True)
            except Exception as e:
                self.ctx.logger.debug("Backup cleanup skipped for %s: %s", bak, e)

    # Alias used by batch ops examples
    def write_raw(self, path: Path, text: str) -> None:
        """Convenience: write with defaults (no backups)."""
        self.write_text(path, text, WriteOptions(make_backup=False))

    def rename(self, old: Path, new: Path, delete_obsolete: bool = False, obsolete_patterns: tuple[str, ...] = ()) -> None:
        """
        Rename a file. If delete_obsolete=True, remove files matching obsolete_patterns
        that are derived from the old name (e.g., stale sidecars).
        """
        new.parent.mkdir(parents=True, exist_ok=True)
        old.replace(new)
        if delete_obsolete and obsolete_patterns:
            for pat in obsolete_patterns:
                for p in old.parent.glob(pat):
                    try:
                        p.unlink()
                    except Exception as e:
                        self.ctx.logger.debug("Could not remove obsolete %s: %s", p, e)

    # ---- Internals -------------------------------------------------------

    def _bak_path(self, path: Path) -> Path:
        return path.with_suffix(path.suffix + ".bak")

    def _write_temp(self, folder: Path, text: str, encoding: str, newline: Optional[str]) -> Path:
        """
        Write text to a temporary file within 'folder'. Return the temp Path.
        Ensures data is flushed and fsynced before returning.
        """
        # NamedTemporaryFile with delete=False to keep control of replace()
        fd, tmp_name = tempfile.mkstemp(prefix=".tmp_", dir=str(folder))
        tmp_path = Path(tmp_name)
        try:
            with io.open(fd, mode="w", encoding=encoding, newline=newline) as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
        except Exception:
            # Ensure temp is cleaned on failure
            try:
                tmp_path.unlink(missing_ok=True)
            finally:
                raise
        return tmp_path

    def _atomic_replace(self, src_tmp: Path, dst: Path) -> None:
        """
        Atomically replace dst with src_tmp (must be same filesystem/dir).
        """
        # On Windows, Path.replace is atomic if same volume and no cross-dir moves.
        src_tmp.replace(dst)
