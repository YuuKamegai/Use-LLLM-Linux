import json
import tarfile

from tools.linux.release import build_release


def test_archive_contains_assets_not_private_files(tmp_path):
    archive = build_release(tmp_path, "test-1")
    with tarfile.open(archive) as tar:
        names = tar.getnames()
        assert "manifest.json" in names
        assert "Start-WebUI.sh" in names
        assert "docs/superpowers/verification/2026-10-19-linux-edition.md" in names
        assert "src/use_lllm/general/static/app.js" in names
        assert any("vendor/fonts/" in name for name in names)
        assert not any(".venv/" in n or ".codex/" in n or "__pycache__" in n for n in names)
        manifest = json.load(tar.extractfile("manifest.json"))
        assert manifest["python_version"] == "3.12.13"
        assert manifest["release_id"] == "test-1"


def test_invalid_release_id_rejected(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        build_release(tmp_path, "../escape")
