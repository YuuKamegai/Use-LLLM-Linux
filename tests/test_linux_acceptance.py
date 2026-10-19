import sys

import pytest


@pytest.mark.skipif(sys.platform != "linux", reason="Real Linux process lifecycle")
def test_double_start_reuses_owned_server_and_stops(tmp_path, monkeypatch):
    from use_lllm.linux.launcher import start, status, stop
    for name, directory in [("HOME", tmp_path), ("XDG_RUNTIME_DIR", tmp_path / "run"),
                             ("XDG_STATE_HOME", tmp_path / "state"),
                             ("USE_LLLM_DATA_DIR", tmp_path / "data")]:
        monkeypatch.setenv(name, str(directory))
    try:
        assert start(open_browser=False) == 0
        first = status()
        assert first["ready"]
        from tools.linux.deploy import update_release
        with pytest.raises(RuntimeError, match="Stop Use-LLLM"):
            update_release(tmp_path / "not-needed.tar.gz", home=tmp_path,
                           uv_executable=tmp_path / "uv")
        assert start(open_browser=False) == 0
        assert status() == first
        assert stop() == 0
        assert not status()["running"]
    finally:
        if status()["running"]:
            stop()


@pytest.mark.skipif(sys.platform != "linux", reason="Real POSIX concurrent process startup")
def test_concurrent_start_has_one_server(tmp_path, monkeypatch):
    import subprocess

    from use_lllm.linux.launcher import status, stop
    for name, directory in [("HOME", tmp_path), ("XDG_RUNTIME_DIR", tmp_path / "run"),
                             ("XDG_STATE_HOME", tmp_path / "state"),
                             ("USE_LLLM_DATA_DIR", tmp_path / "data")]:
        monkeypatch.setenv(name, str(directory))
    command = [sys.executable, "-m", "use_lllm.linux.launcher", "start", "--no-browser"]
    processes = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for _ in range(2)]
    try:
        results = [process.communicate(timeout=40) for process in processes]
        assert all(process.returncode == 0 for process in processes), results
        assert results[0][0] == results[1][0]
        assert status()["ready"]
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
        if status()["running"]:
            stop()


def test_browser_fixture_python_is_platform_aware():
    from pathlib import Path
    text = (Path(__file__).parent / "test_general_browser.cjs").read_text(encoding="utf-8")
    assert 'process.platform === "win32"' in text
    assert "PLAYWRIGHT_BROWSER_CHANNEL" in text
