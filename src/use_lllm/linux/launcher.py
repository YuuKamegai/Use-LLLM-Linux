"""Start and stop only this user's verified Linux WebUI instance."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid
import webbrowser
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

from use_lllm.core.platform_paths import ensure_private_directory, private_file, resolve_paths
from use_lllm.linux.instance import (
    InstanceRecord,
    management_lock,
    process_matches,
    read_record,
    start_ticks,
    write_record,
)


def probe_url(url: str) -> dict:
    with build_opener(ProxyHandler({})).open(url, timeout=1) as response:
        return json.loads(response.read(16384))


def healthy(record: InstanceRecord, *, probe=probe_url) -> bool:
    try:
        data = probe(record.url() + "api/launcher-health")
        return (data.get("application") == "use-lllm-webui" and data.get("static_ready") is True
                and data.get("instance_id") == record.instance_id
                and data.get("release_id") == record.release_id)
    except (OSError, ValueError):
        return False


def wait_ready(check, *, clock=time.monotonic, sleep=time.sleep, timeout=30.0) -> bool:
    deadline = clock() + timeout
    while clock() < deadline:
        if check():
            return True
        sleep(0.2)
    return False


def _port() -> int:
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", 8765))
        except OSError:
            sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def server_log_config(path: str) -> dict:
    return {"version": 1, "disable_existing_loggers": False,
            "formatters": {"basic": {"format": "%(asctime)s %(levelname)s %(message)s"}},
            "handlers": {"file": {"class": "logging.handlers.RotatingFileHandler",
                "filename": path, "maxBytes": 5 * 1024 * 1024, "backupCount": 3,
                "encoding": "utf-8", "formatter": "basic"}},
            "root": {"handlers": ["file"], "level": "INFO"},
            "loggers": {"uvicorn": {"handlers": [], "propagate": True},
                        "uvicorn.access": {"handlers": [], "propagate": False}}}


def _browser(url: str) -> None:
    if not webbrowser.open(url):
        print(f"Open this URL: {url}", file=sys.stderr)


def start(*, open_browser: bool = True) -> int:
    paths = resolve_paths()
    with management_lock(paths.runtime_dir):
        path = paths.runtime_dir / "instance.json"
        existing = read_record(path)
        if existing and process_matches(existing):
            if not healthy(existing):
                raise RuntimeError("Owned server is not ready; check logs or stop it before retrying.")
            if open_browser:
                _browser(existing.url())
            print(existing.url())
            return 0
        ensure_private_directory(paths.state_dir / "logs")
        log = paths.state_dir / "logs/server.log"
        log.touch(mode=0o600, exist_ok=True)
        private_file(log)
        release_id = Path(sys.prefix).parent.name
        for _ in range(3):
            port = _port()
            identifier = str(uuid.uuid4())
            env = dict(os.environ, USE_LLLM_WEB_PORT=str(port), USE_LLLM_INSTANCE_ID=identifier,
                       USE_LLLM_RELEASE_ID=release_id, USE_LLLM_LOG_PATH=str(log))
            child = subprocess.Popen([sys.executable, "-m", "use_lllm", "serve", "--port", str(port)],
                env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, start_new_session=True)
            published = False
            try:
                record = InstanceRecord(child.pid, os.getuid(), start_ticks(child.pid),
                                        port, identifier, release_id)
                ready = wait_ready(lambda child=child, record=record: child.poll() is not None or healthy(record))
                if ready and child.poll() is None and healthy(record):
                    write_record(path, record)
                    published = True
                    if open_browser:
                        _browser(record.url())
                    print(record.url())
                    return 0
            finally:
                if child.poll() is None and not published:
                    child.terminate()
                    try:
                        child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        raise RuntimeError(f"Server did not stop. Check {log}") from None
        raise RuntimeError(f"Server failed to start. Check {log}")


def status() -> dict[str, object]:
    record = read_record(resolve_paths().runtime_dir / "instance.json")
    running = bool(record and process_matches(record))
    return {"running": running, "ready": bool(running and healthy(record)),
            "url": record.url() if running else None}


def stop() -> int:
    paths = resolve_paths()
    with management_lock(paths.runtime_dir):
        path = paths.runtime_dir / "instance.json"
        record = read_record(path)
        if not record or not process_matches(record):
            return 1
        descriptor = os.pidfd_open(record.pid)
        try:
            if not process_matches(record):
                return 3
            signal.pidfd_send_signal(descriptor, signal.SIGTERM)
            if not wait_ready(lambda: not process_matches(record), timeout=10):
                raise RuntimeError("Server did not stop within 10 seconds.")
        finally:
            os.close(descriptor)
        path.unlink(missing_ok=True)
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "stop", "status"])
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if sys.platform != "linux":
        parser.error("This launcher requires Linux.")
    os.umask(0o077)
    try:
        if args.action == "status":
            result = status()
            print(json.dumps(result))
            return 0 if result["running"] else 1
        return stop() if args.action == "stop" else start(open_browser=not args.no_browser)
    except (OSError, RuntimeError) as exc:
        message = str(exc)
        print(message, file=sys.stderr)
        notifier = shutil.which("notify-send")
        if notifier:
            subprocess.run([notifier, "Use-LLLM", message], check=False, timeout=3)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
