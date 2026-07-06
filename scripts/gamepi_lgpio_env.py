"""Prepare a writable cwd before importing lgpio (creates .lgd-nfy* notify pipes)."""

from __future__ import annotations

import os
from pathlib import Path


def prepare_lgpio_runtime() -> Path:
    lgpio_dir = Path(os.environ.get("GAMEPI_LGPIO_DIR", "/var/lib/gamepi"))
    lgpio_dir.mkdir(parents=True, exist_ok=True)
    os.chdir(lgpio_dir)
    return lgpio_dir
