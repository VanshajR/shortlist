"""Read .env into the environment for local runs. Values already set win, so CI
secrets and shell exports aren't overridden. Done by hand rather than by
sourcing the file in a shell: connection strings contain `&`."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
