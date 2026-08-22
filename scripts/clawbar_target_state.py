"""Persist current and verified-fallback Gateway Targets with distinct lifecycles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

if __package__:
    from .clawbar_snapshot import atomic_write_snapshot, load_snapshot
else:
    from clawbar_snapshot import atomic_write_snapshot, load_snapshot


@dataclass(frozen=True)
class GatewayTargetState:
    snapshot_path: Path
    schema_version: int

    @property
    def current_path(self) -> Path:
        return self.snapshot_path.with_name("gateway-target.json")

    @property
    def verified_fallback_path(self) -> Path:
        return self.snapshot_path.with_name("gateway-verified-target.json")

    def record_success(
        self,
        snapshot_generated_at: str,
        source: str,
        current_url: str | None,
        *,
        verified_fallback_url: str | None = None,
    ) -> None:
        if current_url is not None:
            _require_safe_gateway_url(current_url)
        if verified_fallback_url is not None:
            _require_safe_gateway_url(verified_fallback_url)
            if source != "tailscale":
                raise ValueError("only a Tailscale target can be a verified fallback")
            atomic_write_snapshot(
                self.verified_fallback_path,
                {
                    "schemaVersion": self.schema_version,
                    "source": "tailscale",
                    "url": verified_fallback_url,
                },
            )
        if current_url is not None:
            atomic_write_snapshot(
                self.current_path,
                {
                    "schemaVersion": self.schema_version,
                    "snapshotGeneratedAt": snapshot_generated_at,
                    "source": source,
                    "url": current_url,
                },
            )

    def load_verified_fallback(self) -> str | None:
        state = load_snapshot(self.verified_fallback_path, self.schema_version)
        if not state or state.get("source") != "tailscale":
            return None
        url = state.get("url")
        return url if isinstance(url, str) and _safe_gateway_url(url) else None

    def current_url(self, snapshot_generated_at: str | None) -> str | None:
        state = load_snapshot(self.current_path, self.schema_version)
        if not state or state.get("snapshotGeneratedAt") != snapshot_generated_at:
            return None
        url = state.get("url")
        return url if isinstance(url, str) and _safe_gateway_url(url) else None


def collected_target_url(status: dict[str, Any], fallback_url: str | None) -> str | None:
    rpc = status.get("rpc")
    value = rpc.get("url") if isinstance(rpc, dict) else None
    if not isinstance(value, str):
        value = fallback_url
    return value if isinstance(value, str) and _safe_gateway_url(value) else None


def _require_safe_gateway_url(url: str) -> None:
    if not _safe_gateway_url(url):
        raise ValueError(
            "Gateway Target URL must be a ws or wss URL with a host and no credentials, query, or fragment"
        )


def _safe_gateway_url(url: str) -> bool:
    parsed = urlsplit(url)
    return (
        parsed.scheme in {"ws", "wss"}
        and parsed.hostname is not None
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
    )
