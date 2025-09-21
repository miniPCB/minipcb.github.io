import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # repo root
sys.path.insert(0, str(ROOT))               # make 'scripts' importable

from scripts.minipcb_catalog.main import main

if __name__ == "__main__":
    raise SystemExit(main())
