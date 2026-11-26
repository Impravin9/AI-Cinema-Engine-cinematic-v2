"""Safe subprocess execution for the preserved legacy rendering engines."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence


class EngineRunError(RuntimeError):
    pass


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def run_engine(script_name: str, arguments: Sequence[str]) -> int:
    root = project_root()
    engine = root / script_name
    if not engine.is_file():
        raise EngineRunError(f"Renderer not found: {engine}")

    command = [sys.executable, str(engine), *map(str, arguments)]
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    print("\n[cinema] Launching:", subprocess.list2cmdline(command), flush=True)
    print("[cinema] Working directory:", root, flush=True)

    try:
        completed = subprocess.run(command, cwd=root, env=env, check=False)
    except KeyboardInterrupt:
        print("\n[cinema] Rendering interrupted by user.", flush=True)
        return 130
    except OSError as exc:
        raise EngineRunError(f"Could not start {script_name}: {exc}") from exc

    if completed.returncode:
        raise EngineRunError(
            f"{script_name} exited with code {completed.returncode}. "
            "The original renderer reported the error above; fix that error before retrying."
        )
    return completed.returncode
