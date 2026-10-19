import json
from dataclasses import replace
from unittest.mock import patch

import pytest

from tests.test_secret_store import Collection
from use_lllm.core.endpoints import Endpoint
from use_lllm.core.secret_store import SecretServiceStore
from use_lllm.core.settings_store import Settings, default_settings, load_settings, save_settings


def azure():
    return Endpoint("azure", "https://example.openai.azure.com", trust="cloud_allowed",
                    default_model="deployment", provider="azure_openai", api_key="PRIVATE-TEST")


def settings():
    return Settings(default_settings().endpoints + (azure(),), "azure", ())


def test_switch_to_ollama_preserves_locked_reference(tmp_path):
    collection = Collection()
    store = SecretServiceStore(collection=collection)
    path = tmp_path / "settings.json"
    save_settings(path, settings(), secret_store=store)
    original = json.loads(path.read_text())["endpoints"][1]["secret_reference"]
    assert "PRIVATE-TEST" not in path.read_text()
    collection.locked = True
    loaded = load_settings(path, secret_store=store)
    assert not loaded.endpoints[1].available
    save_settings(path, replace(loaded, selected_endpoint="local"), secret_store=store)
    assert json.loads(path.read_text())["endpoints"][1]["secret_reference"] == original


def test_failed_replace_keeps_old_secret_and_settings(tmp_path):
    collection = Collection()
    store = SecretServiceStore(collection=collection)
    path = tmp_path / "settings.json"
    save_settings(path, settings(), secret_store=store)
    original = path.read_bytes()
    loaded = load_settings(path, secret_store=store)
    updated = replace(loaded, endpoints=(loaded.endpoints[0],
                      replace(loaded.endpoints[1], api_key="NEW-PRIVATE")))
    with patch("use_lllm.core.settings_store.os.replace", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            save_settings(path, updated, secret_store=store)
    assert path.read_bytes() == original
    assert len(collection.values) == 1


def test_rename_keeps_credential_id_and_delete_removes_secret(tmp_path):
    collection = Collection()
    store = SecretServiceStore(collection=collection)
    path = tmp_path / "settings.json"
    save_settings(path, settings(), secret_store=store)
    loaded = load_settings(path, secret_store=store)
    endpoint = loaded.endpoints[1]
    updated = replace(loaded, endpoints=(loaded.endpoints[0], replace(endpoint, name="renamed")),
                      selected_endpoint="renamed")
    save_settings(path, updated, secret_store=store)
    assert load_settings(path, secret_store=store).endpoints[1].credential_id == endpoint.credential_id
    assert len(collection.values) == 1
    save_settings(path, default_settings(), secret_store=store)
    assert not collection.values


def test_imported_dpapi_does_not_crash_linux(tmp_path):
    path = tmp_path / "settings.json"
    data = {"endpoints": [{"name": "azure", "base_url": "https://example.openai.azure.com",
            "provider": "azure_openai", "trust": "cloud_allowed", "default_model": "dep",
            "api_key_protected": "dpapi-current-user-v1:unknown"}], "selected_endpoint": "azure"}
    path.write_text(json.dumps(data))
    store = SecretServiceStore(collection=Collection())
    loaded = load_settings(path, secret_store=store)
    assert not loaded.endpoints[0].available
    save_settings(path, loaded, secret_store=store)
    assert "dpapi-current-user-v1:unknown" in path.read_text()


def test_keyring_locked_after_load_can_switch_to_ollama(tmp_path):
    collection = Collection()
    store = SecretServiceStore(collection=collection)
    path = tmp_path / "settings.json"
    save_settings(path, settings(), secret_store=store)
    loaded = load_settings(path, secret_store=store)
    assert loaded.endpoints[1].api_key == "PRIVATE-TEST"
    collection.locked = True
    save_settings(path, replace(loaded, selected_endpoint="local"), secret_store=store)
    assert json.loads(path.read_text())["selected_endpoint"] == "local"


def test_locked_selected_azure_still_serves_settings(tmp_path):
    from tests.test_general_api import FakeOllama, FakeRegistry, secure_client
    from use_lllm.core.sessions import SessionStore
    from use_lllm.general.api import create_general_app
    store = SecretServiceStore(collection=Collection())
    path = tmp_path / "settings.json"
    save_settings(path, settings(), secret_store=store)
    store._collection.locked = True
    with patch("use_lllm.core.settings_store.get_secret_store", return_value=store):
        app = create_general_app(session_store=SessionStore(tmp_path), settings_path=path,
                                 registry_factory=FakeRegistry, ollama_factory=lambda _: FakeOllama())
        with secure_client(app) as client:
            result = client.get("/api/settings")
            assert result.status_code == 200
            assert result.json()["endpoints"][1]["available"] is False
            assert "secret-service-v1" not in result.text
            assert client.post("/api/endpoints/local/select").status_code == 200
