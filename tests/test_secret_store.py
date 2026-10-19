import os

import pytest

from use_lllm.core.secret_store import DPAPIStore, SecretServiceStore, SecretUnavailable


class Collection:
    def __init__(self):
        self.locked = False
        self.values = {}

    def is_locked(self):
        return self.locked

    def search_items(self, attributes):
        return [v for k, v in self.values.items() if k == attributes["reference"]]

    def create_item(self, label, attributes, secret, replace=False):
        owner = self
        key = attributes["reference"]

        class Item:
            def get_secret(self):
                return secret

            def delete(self):
                del owner.values[key]

        self.values[key] = Item()


def test_secret_service_roundtrip():
    store = SecretServiceStore(collection=Collection())
    ref = store.write("test-private-key")
    assert ref.startswith("secret-service-v1:")
    assert store.read(ref) == "test-private-key"
    store.delete(ref)
    with pytest.raises(SecretUnavailable):
        store.read(ref)


def test_locked_collection_does_not_prompt_indefinitely():
    collection = Collection()
    store = SecretServiceStore(collection=collection)
    collection.locked = True
    with pytest.raises(SecretUnavailable, match="locked"):
        store.write("private")
    assert not collection.values


def test_no_fallback_backend():
    with pytest.raises(SecretUnavailable):
        SecretServiceStore(collection=Collection()).read("plaintext:private")


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI")
def test_windows_dpapi_roundtrip_unchanged():
    store = DPAPIStore()
    assert store.read(store.write("test-secret")) == "test-secret"
