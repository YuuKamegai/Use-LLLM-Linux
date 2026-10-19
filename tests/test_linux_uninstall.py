import os
from pathlib import Path

import pytest

from tools.linux.deploy import install_release, uninstall
from tools.linux.release import build_release


@pytest.mark.skipif(os.name == "nt", reason="POSIX installation")
def test_default_uninstall_preserves_data_and_secrets(tmp_path):
    home = tmp_path / "home"
    data = home / ".config/use-lllm/settings.json"
    data.parent.mkdir(parents=True)
    data.write_text('{"secret_reference":"keep"}')
    archive = build_release(tmp_path / "dist", "remove")
    install_release(archive, home=home, uv_executable=Path("uv"),
                    runner=lambda *a, **k: None, smoke=lambda _: None)
    uninstall(home=home)
    assert data.read_text() == '{"secret_reference":"keep"}'
    assert not (home / "Use-LLLM-Linux").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlinks")
def test_symlink_root_is_not_recursively_removed(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep").touch()
    (home / "Use-LLLM-Linux").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        uninstall(home=home)
    assert (outside / "keep").exists()
