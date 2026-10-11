#!/usr/bin/env python3
"""
miniPCB KiCad Script Launcher

A small Tkinter GUI for:
1. Selecting a Python script/exporter.
2. Browsing to a KiCad .kicad_sch schematic.
3. Running the selected script against the selected schematic.
4. Displaying stdout/stderr in a status window.

The launcher automatically scans its own folder for .py files and remembers
the most recently used script and schematic folder.

No third-party Python packages are required.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


APP_TITLE = "miniPCB KiCad Script Launcher"
CONFIG_FILENAME = ".minipcb_kicad_launcher.json"


class KiCadScriptLauncher(tk.Tk):
    def __init__(self) -> None:
        super().__init__()

        self.title(APP_TITLE)
        self.geometry("900x620")
        self.minsize(760, 520)

        self.launcher_path = Path(__file__).resolve()
        self.script_dir = self.launcher_path.parent
        self.config_path = self.script_dir / CONFIG_FILENAME

        self.config_data = self.load_config()

        self.script_var = tk.StringVar()
        self.schematic_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready.")

        self.build_ui()
        self.refresh_scripts()
        self.restore_last_selection()

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def load_config(self) -> dict:
        try:
            if self.config_path.exists():
                return json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def save_config(self) -> None:
        data = {
            "last_script": self.script_var.get(),
            "last_schematic": self.schematic_var.get(),
        }
        try:
            self.config_path.write_text(
                json.dumps(data, indent=2),
                encoding="utf-8",
            )
        except Exception:
            # Launcher functionality should not fail because settings
            # could not be written.
            pass

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def build_ui(self) -> None:
        outer = ttk.Frame(self, padding=16)
        outer.pack(fill="both", expand=True)

        title = ttk.Label(
            outer,
            text="miniPCB KiCad Script Launcher",
            font=("Segoe UI", 16, "bold"),
        )
        title.pack(anchor="w", pady=(0, 14))

        # Script selector
        script_frame = ttk.LabelFrame(outer, text="1. Python Script", padding=12)
        script_frame.pack(fill="x", pady=(0, 12))

        script_row = ttk.Frame(script_frame)
        script_row.pack(fill="x")

        self.script_combo = ttk.Combobox(
            script_row,
            textvariable=self.script_var,
            state="readonly",
        )
        self.script_combo.pack(side="left", fill="x", expand=True)

        ttk.Button(
            script_row,
            text="Refresh",
            command=self.refresh_scripts,
        ).pack(side="left", padx=(8, 0))

        ttk.Button(
            script_row,
            text="Browse...",
            command=self.browse_script,
        ).pack(side="left", padx=(8, 0))

        # Schematic selector
        schematic_frame = ttk.LabelFrame(
            outer,
            text="2. KiCad Schematic",
            padding=12,
        )
        schematic_frame.pack(fill="x", pady=(0, 12))

        schematic_row = ttk.Frame(schematic_frame)
        schematic_row.pack(fill="x")

        schematic_entry = ttk.Entry(
            schematic_row,
            textvariable=self.schematic_var,
        )
        schematic_entry.pack(side="left", fill="x", expand=True)

        ttk.Button(
            schematic_row,
            text="Browse...",
            command=self.browse_schematic,
        ).pack(side="left", padx=(8, 0))

        # Run controls
        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=(0, 12))

        self.run_button = ttk.Button(
            controls,
            text="Run Script",
            command=self.run_selected_script,
        )
        self.run_button.pack(side="left")

        ttk.Button(
            controls,
            text="Clear Output",
            command=self.clear_output,
        ).pack(side="left", padx=(8, 0))

        ttk.Label(
            controls,
            textvariable=self.status_var,
        ).pack(side="left", padx=(16, 0))

        # Output window
        output_frame = ttk.LabelFrame(outer, text="Output", padding=8)
        output_frame.pack(fill="both", expand=True)

        self.output_text = tk.Text(
            output_frame,
            wrap="word",
            font=("Consolas", 10),
            state="disabled",
        )
        self.output_text.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(
            output_frame,
            orient="vertical",
            command=self.output_text.yview,
        )
        scrollbar.pack(side="right", fill="y")
        self.output_text.configure(yscrollcommand=scrollbar.set)

    # ------------------------------------------------------------------
    # Script selection
    # ------------------------------------------------------------------

    def discover_scripts(self) -> list[Path]:
        scripts = []

        for path in sorted(self.script_dir.glob("*.py")):
            if path.resolve() == self.launcher_path:
                continue
            if path.name.startswith("_"):
                continue
            scripts.append(path)

        return scripts

    def refresh_scripts(self) -> None:
        scripts = self.discover_scripts()
        names = [p.name for p in scripts]

        self.script_combo["values"] = names

        current = self.script_var.get()

        if current in names:
            return

        preferred = "minipcb_kicad_sch_md.py"
        if preferred in names:
            self.script_var.set(preferred)
        elif names:
            self.script_var.set(names[0])
        else:
            self.script_var.set("")

    def browse_script(self) -> None:
        initial_dir = self.script_dir

        filename = filedialog.askopenfilename(
            title="Select Python Script",
            initialdir=initial_dir,
            filetypes=[
                ("Python scripts", "*.py"),
                ("All files", "*.*"),
            ],
        )

        if not filename:
            return

        path = Path(filename).resolve()

        # External scripts are allowed. Store the full path in that case.
        if path.parent == self.script_dir:
            value = path.name
        else:
            value = str(path)

        current_values = list(self.script_combo["values"])
        if value not in current_values:
            current_values.append(value)
            self.script_combo["values"] = current_values

        self.script_var.set(value)
        self.save_config()

    # ------------------------------------------------------------------
    # Schematic selection
    # ------------------------------------------------------------------

    def browse_schematic(self) -> None:
        last = self.schematic_var.get().strip()

        if last:
            candidate = Path(last)
            initial_dir = (
                candidate.parent
                if candidate.parent.exists()
                else Path.cwd()
            )
        else:
            initial_dir = Path.cwd()

        filename = filedialog.askopenfilename(
            title="Select KiCad Schematic",
            initialdir=initial_dir,
            filetypes=[
                ("KiCad schematics", "*.kicad_sch"),
                ("All files", "*.*"),
            ],
        )

        if filename:
            self.schematic_var.set(filename)
            self.save_config()

    # ------------------------------------------------------------------
    # Running scripts
    # ------------------------------------------------------------------

    def resolve_script_path(self) -> Path:
        selected = self.script_var.get().strip()

        if not selected:
            raise ValueError("Select a Python script.")

        path = Path(selected)

        if not path.is_absolute():
            path = self.script_dir / path

        return path.resolve()

    def validate_inputs(self) -> tuple[Path, Path]:
        script = self.resolve_script_path()

        if not script.exists():
            raise FileNotFoundError(f"Python script not found:\n{script}")

        schematic_text = self.schematic_var.get().strip()
        if not schematic_text:
            raise ValueError("Select a KiCad schematic.")

        schematic = Path(schematic_text).resolve()

        if not schematic.exists():
            raise FileNotFoundError(f"KiCad schematic not found:\n{schematic}")

        if schematic.suffix.casefold() != ".kicad_sch":
            raise ValueError("Selected schematic must be a .kicad_sch file.")

        return script, schematic

    def run_selected_script(self) -> None:
        try:
            script, schematic = self.validate_inputs()
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return

        self.save_config()
        self.run_button.configure(state="disabled")
        self.status_var.set("Running...")

        self.append_output(
            "\n"
            + "=" * 78
            + "\n"
            + f"Script:    {script}\n"
            + f"Schematic: {schematic}\n"
            + "=" * 78
            + "\n\n"
        )

        thread = threading.Thread(
            target=self.run_process,
            args=(script, schematic),
            daemon=True,
        )
        thread.start()

    def run_process(self, script: Path, schematic: Path) -> None:
        command = [
            sys.executable,
            str(script),
            str(schematic),
        ]

        try:
            process = subprocess.Popen(
                command,
                cwd=str(script.parent),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )

            assert process.stdout is not None

            for line in process.stdout:
                self.after(0, self.append_output, line)

            return_code = process.wait()

            if return_code == 0:
                self.after(
                    0,
                    self.process_finished,
                    True,
                    "Complete.",
                )
            else:
                self.after(
                    0,
                    self.process_finished,
                    False,
                    f"Script exited with code {return_code}.",
                )

        except Exception as exc:
            self.after(
                0,
                self.process_finished,
                False,
                f"Could not run script: {exc}",
            )

    def process_finished(self, success: bool, message: str) -> None:
        self.run_button.configure(state="normal")
        self.status_var.set(message)

        self.append_output(f"\n{message}\n")

        if not success:
            messagebox.showerror(APP_TITLE, message)

    # ------------------------------------------------------------------
    # Output helpers
    # ------------------------------------------------------------------

    def append_output(self, text: str) -> None:
        self.output_text.configure(state="normal")
        self.output_text.insert("end", text)
        self.output_text.see("end")
        self.output_text.configure(state="disabled")

    def clear_output(self) -> None:
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.configure(state="disabled")

    # ------------------------------------------------------------------
    # Restore state
    # ------------------------------------------------------------------

    def restore_last_selection(self) -> None:
        last_script = self.config_data.get("last_script", "")
        last_schematic = self.config_data.get("last_schematic", "")

        values = list(self.script_combo["values"])

        if last_script:
            path = Path(last_script)
            valid = (
                last_script in values
                or (path.is_absolute() and path.exists())
            )
            if valid:
                if last_script not in values:
                    values.append(last_script)
                    self.script_combo["values"] = values
                self.script_var.set(last_script)

        if last_schematic:
            self.schematic_var.set(last_schematic)


def main() -> int:
    app = KiCadScriptLauncher()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
