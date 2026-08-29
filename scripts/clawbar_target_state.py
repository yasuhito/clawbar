"""Persist a verified-fallback Gateway Target without credentials."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

if __package__:
    from .clawbar_snapshot import atomic_write_snapshot, read_json_document
else:
    from clawbar_snapshot import atomic_write_snapshot, read_json_document


VERIFIED_TARGET_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class GatewayTargetState:
    snapshot_path: Path

    @property
    def verified_fallback_path(self) -> Path:
        return self.snapshot_path.with_name("gateway-verified-target.json")

    @property
    def legacy_current_path(self) -> Path:
        return self.snapshot_path.with_name("gateway-target.json")

    def record_verified_fallback(self, url: str) -> None:
        _require_safe_gateway_url(url)
        atomic_write_snapshot(
            self.verified_fallback_path,
            {
                "schemaVersion": VERIFIED_TARGET_SCHEMA_VERSION,
                "source": "tailscale",
                "url": url,
            },
        )

    def load_verified_fallback(self) -> str | None:
        state = read_json_document(self.verified_fallback_path)
        if (
            not state
            or state.get("schemaVersion") != VERIFIED_TARGET_SCHEMA_VERSION
            or state.get("source") != "tailscale"
        ):
            return None
        url = state.get("url")
        return url if isinstance(url, str) and _safe_gateway_url(url) else None

    def discard_legacy_current_target(self) -> None:
        try:
            self.legacy_current_path.unlink(missing_ok=True)
        except OSError:
            pass


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
