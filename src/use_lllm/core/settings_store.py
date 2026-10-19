"""エンドポイントとMCPサーバー仕様をJSON設定ファイルへ永続化する。"""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from use_lllm.core.config import (
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_URL,
    ConfigurationError,
)
from use_lllm.core.endpoints import PROVIDER_OLLAMA, TRUST_LOOPBACK, Endpoint
from use_lllm.core.platform_paths import ensure_private_directory, private_file
from use_lllm.core.secret_protection import protect_secret, unprotect_secret
from use_lllm.core.secret_store import DPAPIStore, SecretStore, SecretUnavailable, get_secret_store


@dataclass(frozen=True, slots=True)
class MCPServerSpec:
    name: str
    command: str = ""
    args: tuple[str, ...] = ()
    cwd: str | None = None
    env: tuple[tuple[str, str], ...] = ()
    autostart: bool = False
    read_only_auto: bool = False
    #: 外部通信ツール（openWorldHint）を、どのセッションでも通す（実行前の承認は残る）。
    allow_network: bool = False
    transport: str = "stdio"
    url: str | None = None
    headers: tuple[tuple[str, str], ...] = ()
    auth_mode: str = "none"

    def validate(self) -> None:
        if not self.name.strip():
            raise ConfigurationError("MCPサーバー名が空です。")
        if self.transport not in {"stdio", "streamable_http", "sse"}:
            raise ConfigurationError(f"未対応のMCP transportです: {self.transport}")
        if self.transport == "stdio" and not self.command.strip():
            raise ConfigurationError(f"MCPサーバー {self.name} のcommandが空です。")
        if self.transport != "stdio":
            if not (self.url or "").strip().lower().startswith(("http://", "https://")):
                raise ConfigurationError(f"MCPサーバー {self.name} のURLが不正です。")
        if self.auth_mode not in {"none", "oauth"}:
            raise ConfigurationError(f"未対応のMCP認証方式です: {self.auth_mode}")

    def env_dict(self) -> dict[str, str]:
        return {key: value for key, value in self.env}

    def headers_dict(self) -> dict[str, str]:
        return {key: value for key, value in self.headers}


@dataclass(frozen=True, slots=True)
class Settings:
    endpoints: tuple[Endpoint, ...]
    selected_endpoint: str
    mcp_servers: tuple[MCPServerSpec, ...]
    web_search_enabled: bool = False


def default_settings() -> Settings:
    local = Endpoint(
        name="local",
        base_url=DEFAULT_OLLAMA_URL,
        trust=TRUST_LOOPBACK,
        default_model=DEFAULT_OLLAMA_MODEL,
    )
    return Settings(endpoints=(local,), selected_endpoint="local", mcp_servers=())


def _endpoint_to_json(endpoint: Endpoint, store: SecretStore | None = None) -> dict[str, Any]:
    payload = {
        "name": endpoint.name,
        "base_url": endpoint.base_url,
        "trust": endpoint.trust,
        "default_model": endpoint.default_model,
        "provider": endpoint.provider,
        "context_window": endpoint.context_window,
    }
    if store is not None and not isinstance(store, DPAPIStore):
        payload["credential_id"] = endpoint.credential_id
        if endpoint.secret_reference:
            key = "api_key_protected" if endpoint.secret_reference.startswith("dpapi-") else "secret_reference"
            payload[key] = endpoint.secret_reference
        elif endpoint.api_key:
            payload["secret_reference"] = store.write(endpoint.api_key)
    elif endpoint.api_key:
        payload["api_key_protected"] = protect_secret(endpoint.api_key)
    return payload


def _endpoint_from_json(data: dict[str, Any], store: SecretStore | None = None) -> Endpoint:
    protected = data.get("api_key_protected")
    reference = data.get("secret_reference") or protected
    error = None
    if reference and store is not None and not isinstance(store, DPAPIStore):
        try:
            api_key = store.read(str(reference))
        except SecretUnavailable as exc:
            api_key = None
            error = str(exc)
    else:
        api_key = unprotect_secret(str(protected)) if protected else data.get("api_key")
    return Endpoint(
        name=str(data["name"]),
        base_url=str(data["base_url"]),
        trust=str(data.get("trust", TRUST_LOOPBACK)),
        default_model=data.get("default_model"),
        provider=str(data.get("provider", PROVIDER_OLLAMA)),
        api_key=str(api_key) if api_key else None,
        credential_id=str(data.get("credential_id") or __import__("uuid").uuid4()),
        secret_reference=str(reference) if reference else None,
        credential_error=error,
        loaded_api_key=str(api_key) if api_key else None,
        context_window=(
            int(data["context_window"]) if isinstance(data.get("context_window"), int) else None
        ),
    )


def _server_to_json(spec: MCPServerSpec) -> dict[str, Any]:
    return {
        "name": spec.name,
        "command": spec.command,
        "args": list(spec.args),
        "cwd": spec.cwd,
        "env": [list(pair) for pair in spec.env],
        "autostart": spec.autostart,
        "read_only_auto": spec.read_only_auto,
        "allow_network": spec.allow_network,
        "transport": spec.transport,
        "url": spec.url,
        "headers": [list(pair) for pair in spec.headers],
        "auth_mode": spec.auth_mode,
    }


def _server_from_json(data: dict[str, Any]) -> MCPServerSpec:
    return MCPServerSpec(
        name=str(data["name"]),
        command=str(data.get("command", "")),
        args=tuple(str(item) for item in data.get("args", [])),
        cwd=data.get("cwd"),
        env=tuple((str(k), str(v)) for k, v in data.get("env", [])),
        autostart=bool(data.get("autostart", False)),
        read_only_auto=bool(data.get("read_only_auto", False)),
        allow_network=bool(data.get("allow_network", False)),
        transport=str(data.get("transport", "stdio")),
        url=data.get("url"),
        headers=tuple((str(k), str(v)) for k, v in data.get("headers", [])),
        auth_mode=str(data.get("auth_mode", "none")),
    )


def settings_to_json(settings: Settings, *, secret_store: SecretStore | None = None) -> dict[str, Any]:
    secret_store = secret_store or get_secret_store()
    return {
        "endpoints": [_endpoint_to_json(e, secret_store) for e in settings.endpoints],
        "selected_endpoint": settings.selected_endpoint,
        "mcp_servers": [_server_to_json(s) for s in settings.mcp_servers],
        "web_search_enabled": settings.web_search_enabled,
    }


def settings_from_json(data: dict[str, Any], *, secret_store: SecretStore | None = None) -> Settings:
    secret_store = secret_store or get_secret_store()
    try:
        web_enabled = data.get("web_search_enabled", False)
        if type(web_enabled) is not bool:
            raise ValueError("web_search_enabledはbooleanで指定してください。")
        return Settings(
            endpoints=tuple(_endpoint_from_json(e, secret_store) for e in data["endpoints"]),
            selected_endpoint=str(data["selected_endpoint"]),
            mcp_servers=tuple(_server_from_json(s) for s in data.get("mcp_servers", [])),
            web_search_enabled=web_enabled,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigurationError(f"設定の形式が不正です: {exc}") from exc


def load_settings(path: Path, *, secret_store: SecretStore | None = None) -> Settings:
    if not path.exists():
        return default_settings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ConfigurationError(f"設定ファイルを読めません: {path}") from exc
    store = secret_store or get_secret_store()
    settings = settings_from_json(raw, secret_store=store)
    if any(
        isinstance(endpoint, dict) and bool(endpoint.get("api_key"))
        for endpoint in raw.get("endpoints", [])
    ):
        save_settings(path, settings, secret_store=store)
    return settings


def _atomic_json(path: Path, payload: dict) -> None:
    ensure_private_directory(path.parent)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        private_file(temporary)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def save_settings(path: Path, settings: Settings, *, secret_store: SecretStore | None = None) -> None:
    from dataclasses import replace

    store = secret_store or get_secret_store()
    if isinstance(store, DPAPIStore):
        _atomic_json(path, settings_to_json(settings))
        return
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    previous = {e.get("credential_id"): e for e in old.get("endpoints", [])}
    created = []
    endpoints = []
    try:
        for endpoint in settings.endpoints:
            reference = endpoint.secret_reference
            if endpoint.api_key:
                old_ref = previous.get(endpoint.credential_id, {}).get("secret_reference")
                same = bool(old_ref and reference == old_ref
                            and endpoint.loaded_api_key == endpoint.api_key)
                if old_ref and not same:
                    try:
                        same = store.read(old_ref) == endpoint.api_key
                    except SecretUnavailable:
                        pass
                reference = old_ref if same else store.write(endpoint.api_key)
                if not same:
                    created.append(reference)
            endpoints.append(replace(endpoint, secret_reference=reference))
        payload = settings_to_json(replace(settings, endpoints=tuple(endpoints)), secret_store=store)
        retained = {e.get("secret_reference") for e in payload["endpoints"]}
        stale = set(old.get("pending_secret_deletions", []))
        stale.update(e.get("secret_reference") for e in old.get("endpoints", []))
        stale = {ref for ref in stale if ref and ref not in retained}
        payload["pending_secret_deletions"] = sorted(stale)
        _atomic_json(path, payload)
    except Exception:
        for reference in created:
            try:
                store.delete(reference)
            except SecretUnavailable:
                pass
        raise
    remaining = []
    for reference in stale:
        try:
            store.delete(reference)
        except SecretUnavailable:
            remaining.append(reference)
    if remaining != payload["pending_secret_deletions"]:
        payload["pending_secret_deletions"] = remaining
        try:
            _atomic_json(path, payload)
        except OSError:
            pass  # Initial document contains safe cleanup references to retry next time.
