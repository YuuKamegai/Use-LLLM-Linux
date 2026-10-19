"""Explicit OS credential stores without file-based fallback or unlock prompts."""

from __future__ import annotations

import os
import uuid
from typing import Protocol

from use_lllm.core.config import ConfigurationError
from use_lllm.core.secret_protection import protect_secret, unprotect_secret

PREFIX = "secret-service-v1:"


class SecretUnavailable(ConfigurationError):
    pass


class SecretStore(Protocol):
    def read(self, reference: str) -> str: ...
    def write(self, value: str) -> str: ...
    def delete(self, reference: str) -> None: ...


class DPAPIStore:
    def read(self, reference: str) -> str:
        return unprotect_secret(reference)

    def write(self, value: str) -> str:
        return protect_secret(value)

    def delete(self, reference: str) -> None:
        pass  # DPAPI ciphertext is stored in the settings document itself.


class SecretServiceStore:
    def __init__(self, *, collection=None):
        self._collection = collection

    def _get_collection(self):
        try:
            if self._collection is None:
                import secretstorage

                bus = secretstorage.dbus_init()
                self._collection = secretstorage.get_collection_by_alias(bus, "default")
            if self._collection.is_locked():
                raise SecretUnavailable("Secret Service is locked. Unlock Passwords and Keys.")
            return self._collection
        except SecretUnavailable:
            raise
        except Exception:
            raise SecretUnavailable("Secret Service unavailable. Start Passwords and Keys.") from None

    @staticmethod
    def _attributes(reference: str) -> dict[str, str]:
        if not reference.startswith(PREFIX):
            raise SecretUnavailable("Unsupported credential format; re-enter the API key.")
        try:
            uuid.UUID(reference.removeprefix(PREFIX))
        except ValueError:
            raise SecretUnavailable("Invalid credential reference.") from None
        return {"application": "Use-LLLM", "reference": reference}

    def read(self, reference: str) -> str:
        attributes = self._attributes(reference)
        try:
            for item in self._get_collection().search_items(attributes):
                return item.get_secret().decode("utf-8")
        except SecretUnavailable:
            raise
        except Exception:
            raise SecretUnavailable("Secret Service could not read the API key.") from None
        raise SecretUnavailable("API key missing; re-enter the API key.")

    def write(self, value: str) -> str:
        if not value:
            raise SecretUnavailable("Empty API key.")
        reference = PREFIX + str(uuid.uuid4())
        try:
            self._get_collection().create_item(
                "Use-LLLM Azure OpenAI", self._attributes(reference), value.encode(), replace=False
            )
        except SecretUnavailable:
            raise
        except Exception:
            raise SecretUnavailable("Secret Service could not save the API key.") from None
        return reference

    def delete(self, reference: str) -> None:
        attributes = self._attributes(reference)
        try:
            for item in self._get_collection().search_items(attributes):
                item.delete()
        except SecretUnavailable:
            raise
        except Exception:
            raise SecretUnavailable("Secret Service could not delete the API key.") from None


def get_secret_store() -> SecretStore:
    return DPAPIStore() if os.name == "nt" else SecretServiceStore()
