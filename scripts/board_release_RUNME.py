import subprocess
import sys
from pathlib import Path


def main() -> int:
    scripts_dir = Path(__file__).resolve().parent
    repo_root = scripts_dir.parent

    scripts_to_run = [
        "generate_board_lists.py",
        "generate_scrollable_list.py",
        "generate_site_index.py",
    ]

    print(f"Repo root: {repo_root}")

    for script_name in scripts_to_run:
        script_path = scripts_dir / script_name
        print(f"\nRunning {script_name}...")
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=repo_root,
            check=False,
        )
        if result.returncode != 0:
            print(f"Failed: {script_name} (exit {result.returncode})")
            return result.returncode

    print("\nAll scripts completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
