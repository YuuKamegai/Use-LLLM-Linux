"""Owner-verified instance records and process identities."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

from use_lllm.core.platform_paths import ensure_private_directory, private_file


@dataclass(frozen=True)
class InstanceRecord:
    pid: int
    uid: int
    start_ticks: int
    port: int
    instance_id: str
    release_id: str

    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/general/"


def start_ticks(pid: int, proc_root: Path = Path("/proc")) -> int:
    return int((proc_root / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()[19])


def process_matches(record: InstanceRecord, *, proc_root: Path = Path("/proc")) -> bool:
    try:
        process = proc_root / str(record.pid)
        command = (process / "cmdline").read_bytes().split(b"\0")
        return (record.pid > 1 and process.stat().st_uid == record.uid
                and start_ticks(record.pid, proc_root) == record.start_ticks
                and b"use_lllm" in command and b"serve" in command)
    except (OSError, ValueError, IndexError):
        return False


def read_record(path: Path) -> InstanceRecord | None:
    try:
        if path.is_symlink() or path.stat().st_uid != os.getuid():
            return None
        record = InstanceRecord(**json.loads(path.read_text()))
        if record.uid != os.getuid() or not 1 <= record.port <= 65535:
            return None
        return record
    except (OSError, TypeError, ValueError):
        return None


def write_record(path: Path, record: InstanceRecord) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(record)), encoding="utf-8")
    private_file(temporary)
    temporary.replace(path)


@contextmanager
def management_lock(directory: Path):
    import fcntl

    ensure_private_directory(directory)
    descriptor = os.open(directory / "management.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
