"""Platform-specific user locations; never depend on the working directory."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    app_root: Path
    config_dir: Path
    data_dir: Path
    state_dir: Path
    runtime_dir: Path


def resolve_paths(*, platform: str | None = None, home: Path | None = None,
                  environ: Mapping[str, str] | None = None) -> AppPaths:
    platform = platform or sys.platform
    home = home if home is not None else Path.home()
    env = os.environ if environ is None else environ

    def location(name: str, fallback: Path) -> Path:
        value = env.get(name, "")
        return Path(value) if value and Path(value).is_absolute() else fallback

    if platform == "win32":
        data = location("LOCALAPPDATA", home / "AppData/Local") / "Use-LLLM"
        config = state = data
    else:
        data = location("XDG_DATA_HOME", home / ".local/share") / "use-lllm/data"
        config = location("XDG_CONFIG_HOME", home / ".config") / "use-lllm"
        state = location("XDG_STATE_HOME", home / ".local/state") / "use-lllm"
    override = env.get("USE_LLLM_DATA_DIR", "")
    if override:
        override = str(home) + override[1:] if override.startswith("~/") else override
        data = config = Path(override).expanduser().resolve()
    runtime = location("XDG_RUNTIME_DIR", state / "runtime")
    if env.get("XDG_RUNTIME_DIR") and Path(env["XDG_RUNTIME_DIR"]).is_absolute():
        runtime /= "use-lllm"
    return AppPaths(home / "Use-LLLM-Linux", config, data, state, runtime)


def ensure_private_directory(path: Path) -> None:
    if path.is_symlink():
        raise OSError(f"Private directory must not be a symbolic link: {path}")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        if path.stat().st_uid != os.getuid():
            raise PermissionError(f"Directory belongs to another user: {path}")
        path.chmod(0o700)


def private_file(path: Path) -> None:
    if os.name != "nt":
        path.chmod(0o600)
