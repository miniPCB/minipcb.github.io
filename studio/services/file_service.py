import os, shutil, tempfile
from pathlib import Path

class FileService:
    def __init__(self, root: Path):
        self.root = Path(root)

    # Safe write (atomic replace)
    def write_text_atomic(self, path: Path, text: str, encoding: str = "utf-8"):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=path.name, dir=str(path.parent))
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(text)
        os.replace(tmp, path)

    def read_text(self, path: Path, encoding: str = "utf-8") -> str:
        return Path(path).read_text(encoding=encoding)

    def mkdir(self, path: Path):
        Path(path).mkdir(parents=True, exist_ok=True)

    def move(self, src: Path, dst: Path):
        dst = Path(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))

    def delete(self, path: Path):
        p = Path(path)
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()

    def rename(self, src: Path, new_name: str) -> Path:
        src = Path(src)
        dst = src.with_name(new_name)
        os.replace(src, dst)
        return dst
