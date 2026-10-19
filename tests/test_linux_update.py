import io
import os
import tarfile
from pathlib import Path

import pytest

from tools.linux.deploy import _validated, install_release, update_release
from tools.linux.release import build_release


def test_bad_archive_does_not_escape_root(tmp_path):
    archive = tmp_path / "evil.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        item = tarfile.TarInfo("../outside")
        item.size = 1
        tar.addfile(item, io.BytesIO(b"x"))
    with pytest.raises(ValueError, match="Unsafe"):
        _validated(archive)
    assert not (tmp_path.parent / "outside").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX installation")
def test_download_or_enospc_preserves_current(tmp_path):
    home = tmp_path / "home"
    original = build_release(tmp_path / "dist", "original")
    next_release = build_release(tmp_path / "dist", "next")
    old = install_release(original, home=home, uv_executable=Path("uv"),
                          runner=lambda *a, **k: None, smoke=lambda _: None)
    def fail(*a, **k):
        raise OSError("No space left")
    with pytest.raises(OSError):
        update_release(next_release, home=home, uv_executable=Path("uv"), runner=fail,
                       smoke=lambda _: None)
    assert (home / "Use-LLLM-Linux/current").resolve() == old


def test_backup_respects_custom_data_directory(tmp_path, monkeypatch):
    import sqlite3

    from tools.linux.deploy import _backup, locations

    custom = tmp_path / "custom-data"
    custom.mkdir()
    monkeypatch.setenv("USE_LLLM_DATA_DIR", str(custom))
    (custom / "settings.json").write_text('{"test":"preserve"}')
    with sqlite3.connect(custom / "use-lllm.sqlite3") as db:
        db.execute("CREATE TABLE sample(value TEXT)")
        db.execute("INSERT INTO sample VALUES ('preserve')")
    _backup(tmp_path)
    backups = list((locations(tmp_path)["state"] / "backups").iterdir())
    assert (backups[0] / "settings.json").read_text() == '{"test":"preserve"}'
    with sqlite3.connect(backups[0] / "use-lllm.sqlite3") as db:
        assert db.execute("SELECT value FROM sample").fetchone()[0] == "preserve"


@pytest.mark.skipif(os.name == "nt", reason="POSIX installation")
def test_update_does_not_overwrite_stable_launcher(tmp_path, monkeypatch):
    from contextlib import suppress

    home = tmp_path / "home"
    original = build_release(tmp_path / "dist", "original")
    next_release = build_release(tmp_path / "dist", "next")
    install_release(original, home=home, uv_executable=Path("uv"),
                    runner=lambda *a, **k: None, smoke=lambda _: None)
    script = home / "Use-LLLM-Linux/Start-WebUI.sh"
    content = script.read_bytes()
    write = Path.write_bytes
    def disk_full(path, data):
        if path == script:
            write(path, b"truncated")
            raise OSError("disk full")
        return write(path, data)
    monkeypatch.setattr(Path, "write_bytes", disk_full)
    with suppress(OSError):
        update_release(next_release, home=home, uv_executable=Path("uv"),
                       runner=lambda *a, **k: None, smoke=lambda _: None)
    assert script.read_bytes() == content
