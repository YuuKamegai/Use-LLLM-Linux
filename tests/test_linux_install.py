import os
from pathlib import Path

import pytest

from tools.linux.deploy import desktop_entry, install_release
from tools.linux.release import build_release


def test_desktop_exec_quotes_special_home(tmp_path):
    root = tmp_path / '研究室 user%'
    entry = desktop_entry(root / "Start-WebUI.sh")
    assert "user%%" in entry
    assert 'Exec="' in entry
    assert "Terminal=false" in entry


def test_deploy_runtime_fallback_matches_launcher(tmp_path, monkeypatch):
    from tools.linux.deploy import locations
    from use_lllm.core.platform_paths import resolve_paths
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "custom-state"))
    assert locations(tmp_path)["runtime"] == resolve_paths(platform="linux", home=tmp_path).runtime_dir


@pytest.mark.skipif(os.name == "nt", reason="Linux installation requires POSIX symlinks")
def test_setup_creates_venv_at_final_path(tmp_path):
    home = tmp_path / "home"
    archive = build_release(tmp_path / "dist", "test-a")
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        directory = Path(command[command.index("--project") + 1])
        (directory / ".venv/bin").mkdir(parents=True)
        return None

    result = install_release(archive, home=home, uv_executable=Path("uv"),
                             runner=runner, smoke=lambda _: None)
    assert result == home / "Use-LLLM-Linux/releases/test-a"
    assert "--frozen" in calls[0] and "--no-dev" in calls[0]
    assert (home / "Use-LLLM-Linux/current").resolve() == result.resolve()


def test_setup_failure_has_no_current(tmp_path):
    archive = build_release(tmp_path / "dist", "test-fail")
    def fail(*args, **kwargs):
        raise OSError("disk full")
    with pytest.raises(OSError):
        install_release(archive, home=tmp_path / "home", uv_executable=Path("uv"),
                        runner=fail, smoke=lambda _: None)
    assert not (tmp_path / "home/Use-LLLM-Linux/current").exists()
