"""Standard-library-only user installation and transactional release switching."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path, PurePosixPath


def locations(home: Path) -> dict[str, Path]:
    def xdg(key, default):
        value = os.environ.get(key, "")
        return Path(value) if value and Path(value).is_absolute() else home / default
    state = xdg("XDG_STATE_HOME", ".local/state") / "use-lllm"
    runtime = xdg("XDG_RUNTIME_DIR", ".local/state/use-lllm/runtime")
    if not os.environ.get("XDG_RUNTIME_DIR") or not Path(os.environ["XDG_RUNTIME_DIR"]).is_absolute():
        runtime = state / "runtime"
    if os.environ.get("XDG_RUNTIME_DIR") and Path(os.environ["XDG_RUNTIME_DIR"]).is_absolute():
        runtime /= "use-lllm"
    config = xdg("XDG_CONFIG_HOME", ".config") / "use-lllm"
    data = xdg("XDG_DATA_HOME", ".local/share") / "use-lllm/data"
    override = os.environ.get("USE_LLLM_DATA_DIR", "")
    if override:
        override = str(home) + override[1:] if override.startswith("~/") else override
        config = data = Path(override).expanduser().resolve()
    return {"app": home / "Use-LLLM-Linux", "state": state, "runtime": runtime,
            "config": config, "data": data,
            "desktop": xdg("XDG_DATA_HOME", ".local/share") / "applications/use-lllm.desktop",
            "entry": home / ".local/bin/use-lllm-webui"}



def checked_directory(path: Path) -> None:
    # Never resolve away symlinks before checking the user-supplied path.
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError(f"Symbolic link in managed path: {path}")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        if path.stat().st_uid != os.getuid():
            raise PermissionError(f"Not owned by current user: {path}")
        path.chmod(0o700)


@contextmanager
def deployment_lock(home: Path):
    runtime = locations(home)["runtime"]
    checked_directory(runtime)
    if sys.platform != "linux":
        yield  # Portable pure-function and fake-install tests only.
        return
    import fcntl
    fd = os.open(runtime / "management.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            record = runtime / "instance.json"
            if record.is_file():
                data = json.loads(record.read_text())
                proc = Path("/proc") / str(data["pid"])
                try:
                    ticks = int((proc / "stat").read_text().rsplit(")", 1)[1].split()[19])
                    if proc.stat().st_uid == os.getuid() and ticks == data["start_ticks"]:
                        raise RuntimeError("Stop Use-LLLM before updating or uninstalling.")
                except FileNotFoundError:
                    pass
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def desktop_entry(script: Path) -> str:
    value = str(script).replace("\\", "\\\\").replace('"', '\\"')
    value = value.replace("`", "\\`").replace("$", "\\$").replace("%", "%%")
    return ("[Desktop Entry]\nType=Application\nName=Use-LLLM\n"
            f'Exec="{value}"\nTerminal=false\nCategories=Education;Science;\n')


def _files(source: Path) -> dict[str, bytes]:
    if source.is_dir():
        paths = list(source.rglob("*"))
        if any(p.is_symlink() for p in paths):
            raise ValueError("Symlinks not allowed in release")
        return {p.relative_to(source).as_posix(): p.read_bytes() for p in paths if p.is_file()}
    result = {}
    total = 0
    with tarfile.open(source) as archive:
        for item in archive:
            name = PurePosixPath(item.name)
            if (name.is_absolute() or ".." in name.parts or "\\" in item.name
                    or ":" in item.name or item.issym() or item.islnk()
                    or not (item.isfile() or item.isdir())):
                raise ValueError("Unsafe archive member")
            if item.isdir():
                continue
            total += item.size
            if total > 256 * 1024 * 1024 or len(result) > 10000 or item.name in result:
                raise ValueError("Oversized or duplicate archive member")
            result[item.name] = archive.extractfile(item).read()
    return result


def _validated(source: Path) -> tuple[dict, dict[str, bytes]]:
    files = _files(source)
    manifest = json.loads(files.pop("manifest.json"))
    identifier = manifest["release_id"]
    if (manifest.get("schema_version") != 1 or manifest.get("python_version") != "3.12.13"
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", identifier)
            or ".." in identifier):
        raise ValueError("Unsupported release manifest")
    if set(manifest["files"]) != set(files):
        raise ValueError("Release contents differ from manifest")
    for name, content in files.items():
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
            raise ValueError("Unsafe manifest path")
        if hashlib.sha256(content).hexdigest() != manifest["files"][name]:
            raise ValueError("Release checksum mismatch")
    for required in ["Start-WebUI.sh", "Update-Linux.sh", "Uninstall-Linux.sh", "uv.lock",
                     "pyproject.toml", "src/use_lllm/app.py", "tools/linux/deploy.py"]:
        if required not in files:
            raise ValueError(f"Release is missing {required}")
    return manifest, files


def _smoke(release: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="use-lllm-smoke-") as temporary:
        env = dict(os.environ, USE_LLLM_DATA_DIR=temporary, PYTHONPATH=str(release / "src"))
        for key in ["USE_LLLM_INSTANCE_ID", "USE_LLLM_RELEASE_ID", "USE_LLLM_LOG_PATH"]:
            env.pop(key, None)
        code = ('from fastapi.testclient import TestClient; from use_lllm.app import app; '
                'c=TestClient(app,base_url="http://127.0.0.1"); '
                'assert c.get("/general/api/launcher-health").json()["static_ready"]; '
                'assert c.get("/general/").status_code==200')
        subprocess.run([str(release / ".venv/bin/python"), "-c", code],
                       cwd=release, env=env, check=True, timeout=30)


def _publish_file(path: Path, data: bytes, mode: int) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=".use-lllm-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(mode)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _switch(root: Path, target: Path) -> None:
    temporary = root / ".current-next"
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target, target_is_directory=True)
    temporary.replace(root / "current")


def _install(archive: Path, *, home: Path, uv_executable: Path, runner, smoke) -> Path:
    manifest, files = _validated(archive)
    paths = locations(home)
    root = paths["app"]
    checked_directory(root)
    marker = root / ".use-lllm-installation"
    if not marker.exists() and any(root.iterdir()):
        raise ValueError("Existing directory is not a managed Use-LLLM installation")
    marker.touch(mode=0o600)
    checked_directory(root / "releases")
    release = root / "releases" / manifest["release_id"]
    if release.exists() or release.is_symlink():
        raise ValueError("This release already exists; use a distinct release ID")
    checked_directory(release)
    try:
        for name, content in files.items():
            path = release / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            path.chmod(0o755 if name.endswith(".sh") else 0o644)
        (release / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        runner([str(uv_executable), "sync", "--project", str(release), "--frozen", "--no-dev",
                "--python", manifest["python_version"]], check=True)
        smoke(release)
        for name in ["Start-WebUI.sh", "Update-Linux.sh", "Uninstall-Linux.sh"]:
            shim = root / name
            if shim.is_symlink():
                raise ValueError("Unexpected symlink at launcher")
            if not shim.exists():
                _publish_file(shim, files[name], 0o755)
        paths["entry"].parent.mkdir(parents=True, exist_ok=True)
        paths["desktop"].parent.mkdir(parents=True, exist_ok=True)
        if paths["entry"].exists() and not paths["entry"].is_symlink():
            raise ValueError("Refusing to replace an existing executable")
        if paths["entry"].is_symlink() and paths["entry"].resolve() != (root / "Start-WebUI.sh").resolve():
            raise ValueError("Refusing to replace a foreign shortcut")
        if not paths["entry"].is_symlink():
            temporary_entry = paths["entry"].with_suffix(".tmp")
            temporary_entry.unlink(missing_ok=True)
            temporary_entry.symlink_to(root / "Start-WebUI.sh")
            temporary_entry.replace(paths["entry"])
        desktop = paths["desktop"]
        if desktop.is_symlink():
            raise ValueError("Unexpected desktop entry symlink")
        text = desktop_entry(root / "Start-WebUI.sh")
        if desktop.exists() and "X-Use-LLLM-Managed=true" not in desktop.read_text():
            raise ValueError("Refusing to replace a foreign desktop entry")
        if not desktop.exists():
            _publish_file(desktop, (text + "X-Use-LLLM-Managed=true\n").encode(), 0o644)
        _switch(root, release)
        return release
    except Exception:
        (release / ".incomplete").touch()
        raise


def install_release(archive: Path, *, home: Path, uv_executable: Path,
                    runner=subprocess.run, smoke=_smoke) -> Path:
    with deployment_lock(home):
        return _install(archive, home=home, uv_executable=uv_executable, runner=runner, smoke=smoke)


def _backup(home: Path) -> None:
    paths = locations(home)
    backup = paths["state"] / "backups" / str(time.time_ns())
    checked_directory(backup)
    for name in ["settings.json", "setup.json"]:
        source = paths["config"] / name
        if source.exists():
            shutil.copyfile(source, backup / name)
            (backup / name).chmod(0o600)
    source = paths["data"] / "use-lllm.sqlite3"
    if source.exists():
        with sqlite3.connect(source) as original, sqlite3.connect(backup / source.name) as copy:
            original.backup(copy)
        (backup / source.name).chmod(0o600)


def update_release(archive: Path, *, home: Path, uv_executable: Path,
                   runner=subprocess.run, smoke=_smoke) -> Path:
    with deployment_lock(home):
        paths = locations(home)
        current = paths["app"] / "current"
        if not current.is_symlink():
            raise ValueError("No managed installation to update")
        old = current.resolve()
        _backup(home)
        try:
            result = _install(archive, home=home, uv_executable=uv_executable,
                              runner=runner, smoke=smoke)
            smoke(result)
            return result
        except Exception:
            _switch(paths["app"], old)
            raise


def uninstall(*, home: Path, purge_data: bool = False) -> None:
    paths = locations(home)
    root = paths["app"]
    if root.is_symlink() or any(p.is_symlink() for p in root.parents):
        raise ValueError("Refusing to remove symlink installation")
    if not (root / ".use-lllm-installation").is_file():
        raise ValueError("Not a managed installation")
    with deployment_lock(home):
        if purge_data:
            if os.environ.get("USE_LLLM_DATA_DIR"):
                raise ValueError("Custom data directory requires manual data cleanup")
            from use_lllm.core.secret_store import get_secret_store
            config = paths["config"] / "settings.json"
            if config.exists():
                data = json.loads(config.read_text())
                references = [e.get("secret_reference") for e in data.get("endpoints", [])]
                references.extend(data.get("pending_secret_deletions", []))
                for ref in filter(None, references):
                    get_secret_store().delete(ref)
            for directory in [paths["config"], paths["data"]]:
                checked_directory(directory)
                shutil.rmtree(directory)
        if paths["entry"].is_symlink() and paths["entry"].resolve() == (root / "Start-WebUI.sh").resolve():
            paths["entry"].unlink()
        desktop = paths["desktop"]
        if desktop.is_file() and not desktop.is_symlink() and "X-Use-LLLM-Managed=true" in desktop.read_text():
            desktop.unlink()
        checked_directory(root)
        shutil.rmtree(root)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["install", "update", "uninstall"])
    parser.add_argument("archive", nargs="?", type=Path)
    parser.add_argument("--purge-data", action="store_true")
    args = parser.parse_args()
    if sys.platform != "linux" or os.geteuid() == 0:
        parser.error("Run as a normal Linux user, without sudo.")
    os.umask(0o077)
    try:
        if args.action == "uninstall":
            uninstall(home=Path.home(), purge_data=args.purge_data)
        else:
            uv = shutil.which("uv")
            if not uv:
                raise RuntimeError("uv is missing. See docs/linux/README.md.")
            if not args.archive:
                parser.error("Release archive or extracted release directory is required")
            action = install_release if args.action == "install" else update_release
            print(action(args.archive.resolve(), home=Path.home(), uv_executable=Path(uv)))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, KeyError) as exc:
        print(f"Use-LLLM: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
