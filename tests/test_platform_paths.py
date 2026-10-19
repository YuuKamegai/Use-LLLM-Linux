import os

from use_lllm.core.platform_paths import ensure_private_directory, resolve_paths


def test_linux_paths_follow_xdg(tmp_path):
    paths = resolve_paths(platform="linux", home=tmp_path, environ={
        "XDG_DATA_HOME": str(tmp_path / "data"), "XDG_CONFIG_HOME": str(tmp_path / "config")})
    assert paths.app_root == tmp_path / "Use-LLLM-Linux"
    assert paths.config_dir == tmp_path / "config/use-lllm"
    assert paths.data_dir == tmp_path / "data/use-lllm/data"


def test_data_override_keeps_settings_together(tmp_path):
    paths = resolve_paths(platform="linux", home=tmp_path,
                          environ={"USE_LLLM_DATA_DIR": str(tmp_path / "custom")})
    assert paths.data_dir == paths.config_dir == tmp_path / "custom"


def test_windows_paths_unchanged(tmp_path):
    paths = resolve_paths(platform="win32", home=tmp_path, environ={})
    assert paths.data_dir == paths.config_dir == tmp_path / "AppData/Local/Use-LLLM"


def test_relative_xdg_ignored_and_runtime_falls_back(tmp_path):
    paths = resolve_paths(platform="linux", home=tmp_path,
                          environ={"XDG_CONFIG_HOME": "relative"})
    assert paths.config_dir == tmp_path / ".config/use-lllm"
    assert paths.runtime_dir == paths.state_dir / "runtime"


def test_private_directory(tmp_path):
    path = tmp_path / "private"
    ensure_private_directory(path)
    assert path.is_dir()
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o700


def test_home_expansion_uses_injected_home(tmp_path):
    paths = resolve_paths(platform="linux", home=tmp_path,
                          environ={"USE_LLLM_DATA_DIR": "~/research"})
    assert paths.data_dir == tmp_path / "research"
