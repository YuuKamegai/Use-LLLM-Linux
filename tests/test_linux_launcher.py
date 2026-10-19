
from use_lllm.linux.instance import InstanceRecord, process_matches
from use_lllm.linux.launcher import healthy, wait_ready


def test_reused_pid_never_signalled(tmp_path):
    record = InstanceRecord(123, 1000, 42, 8765, "instance", "release")
    assert not process_matches(record, proc_root=tmp_path)


def test_foreign_health_not_reused():
    record = InstanceRecord(123, 1000, 42, 8765, "mine", "release")
    assert not healthy(record, probe=lambda _: {"application": "use-lllm-webui",
        "static_ready": True, "instance_id": "foreign", "release_id": "release"})


def test_owned_health():
    record = InstanceRecord(123, 1000, 42, 8765, "mine", "release")
    assert healthy(record, probe=lambda _: {"application": "use-lllm-webui",
        "static_ready": True, "instance_id": "mine", "release_id": "release"})


def test_timeout_keeps_diagnostic_log():
    ticks = iter([0, 0, 31])
    assert not wait_ready(lambda: False, clock=lambda: next(ticks), sleep=lambda _: None)


def test_ready_without_fixed_delay():
    assert wait_ready(lambda: True, clock=lambda: 0, sleep=lambda _: None)


def test_record_write_failure_does_not_orphan_server(tmp_path, monkeypatch):
    from contextlib import nullcontext

    import pytest

    from use_lllm.core.platform_paths import AppPaths
    from use_lllm.linux import launcher

    class Child:
        pid = 123
        terminated = False

        def poll(self):
            return 0 if self.terminated else None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout):
            return 0

    child = Child()
    paths = AppPaths(tmp_path, tmp_path, tmp_path, tmp_path, tmp_path)
    monkeypatch.setattr(launcher, "resolve_paths", lambda: paths)
    monkeypatch.setattr(launcher, "management_lock", lambda _: nullcontext())
    monkeypatch.setattr(launcher, "read_record", lambda _: None)
    monkeypatch.setattr(launcher, "_port", lambda: 8765)
    monkeypatch.setattr(launcher, "start_ticks", lambda _: 42)
    monkeypatch.setattr(launcher, "healthy", lambda _: True)
    current_uid = launcher.os.getuid() if hasattr(launcher.os, "getuid") else 1000
    monkeypatch.setattr(launcher.os, "getuid", lambda: current_uid, raising=False)
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *a, **k: child)
    def fail(*args):
        raise OSError("disk full")
    monkeypatch.setattr(launcher, "write_record", fail)
    with pytest.raises(OSError):
        launcher.start(open_browser=False)
    assert child.terminated
