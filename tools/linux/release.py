"""Build an allowlisted Linux distribution, without local settings or runtimes."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ("Setup-Linux.sh", "Start-WebUI.sh", "Update-Linux.sh", "Uninstall-Linux.sh")


def build_release(destination: Path, release_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", release_id) or ".." in release_id:
        raise ValueError("Invalid release identifier")
    destination.mkdir(parents=True, exist_ok=True)
    files = {}
    for entry in ("src/use_lllm", "tools/linux", "docs/linux",
                  "docs/superpowers/verification/2026-10-19-linux-edition.md",
                  "pyproject.toml", "uv.lock", "README.md", *SCRIPTS):
        root = ROOT / entry
        if not root.exists():
            raise FileNotFoundError(root)
        for path in sorted(root.rglob("*") if root.is_dir() else [root]):
            if path.is_symlink():
                raise ValueError(f"Distribution symlink is not allowed: {path}")
            if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    manifest = {"schema_version": 1, "release_id": release_id, "python_version": "3.12.13",
                "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    files["manifest.json"] = json.dumps(manifest, indent=2).encode()
    output = destination / f"Use-LLLM-Linux-{release_id}.tar.gz"
    with tarfile.open(output, "w:gz") as tar:
        for name, data in files.items():
            item = tarfile.TarInfo(name)
            item.size = len(data)
            item.mode = 0o755 if name.endswith(".sh") else 0o644
            tar.addfile(item, io.BytesIO(data))
    output.with_suffix(output.suffix + ".sha256").write_text(
        f"{hashlib.sha256(output.read_bytes()).hexdigest()}  {output.name}\n", encoding="ascii")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("release_id")
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    print(build_release(args.output, args.release_id))
