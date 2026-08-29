"""Resolve and verify one OpenClaw Gateway Target without persisting credentials."""

from __future__ import annotations

import ipaddress
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlsplit

if __package__:
    from .clawbar_commands import (
        TAILSCALE_COMMAND,
        CollectionDeadlineExceeded,
        CommandOutputExceeded,
        MAX_COMMAND_STREAM_BYTES,
        run_command,
        seconds_until_deadline,
    )
    from .clawbar_metadata import opaque_candidate_key
    from .clawbar_snapshot import atomic_write_snapshot, last_known_metadata, load_snapshot, snapshot_envelope
else:
    from clawbar_commands import (
        TAILSCALE_COMMAND,
        CollectionDeadlineExceeded,
        CommandOutputExceeded,
        MAX_COMMAND_STREAM_BYTES,
        run_command,
        seconds_until_deadline,
    )
    from clawbar_metadata import opaque_candidate_key
    from clawbar_snapshot import atomic_write_snapshot, last_known_metadata, load_snapshot, snapshot_envelope

# CollectionDeadlineExceeded / CommandOutputExceeded / MAX_COMMAND_STREAM_BYTES / run_command
# は clawbar_commands に移した。既存の呼び出し側とテストのためにここでも再公開する。
__all__ = [
    "CollectionDeadlineExceeded",
    "CommandOutputExceeded",
    "MAX_COMMAND_STREAM_BYTES",
    "run_command",
    "seconds_until_deadline",
]

GATEWAY_PORT = 18789
SETUP_GUIDANCE = "Choose a Tailscale device to verify as your OpenClaw Gateway."
NO_TAILSCALE_GUIDANCE = "Connect Tailscale on this device, then refresh to find Gateway candidates."
KEY_SECRET_ERROR = "Clawbar cannot derive private Gateway Candidate Keys. Repair its local key secret."


@dataclass(frozen=True)
class GatewayTarget:
    url: str
    source: str


def command_option(arguments: Sequence[str], option: str) -> str | None:
    try:
        index = arguments.index(option)
    except ValueError:
        return None
    if index + 1 >= len(arguments):
        return None
    value = arguments[index + 1]
    return value if value and not value.startswith("--") else None


def node_host_target(status: object) -> GatewayTarget | None:
    if not isinstance(status, dict):
        return None
    service = status.get("service")
    if not isinstance(service, dict) or service.get("loaded") is not True:
        return None
    runtime = service.get("runtime")
    if not isinstance(runtime, dict):
        return None
    if runtime.get("status") != "running" and runtime.get("state") != "active":
        return None
    command = service.get("command")
    if not isinstance(command, dict):
        return None
    arguments = command.get("programArguments")
    if not isinstance(arguments, list) or not all(isinstance(value, str) for value in arguments):
        return None
    if not any(arguments[index : index + 2] == ["node", "run"] for index in range(len(arguments) - 1)):
        return None

    host = command_option(arguments, "--host")
    port_text = command_option(arguments, "--port")
    if host is None or port_text is None or any(character in host for character in "/@?#"):
        return None
    try:
        port = int(port_text)
    except ValueError:
        return None
    if not 1 <= port <= 65535:
        return None

    context_path = command_option(arguments, "--context-path") or ""
    if context_path and (not context_path.startswith("/") or "?" in context_path or "#" in context_path):
        return None
    try:
        parsed_ip = ipaddress.ip_address(host)
        url_host = f"[{host}]" if parsed_ip.version == 6 else host
    except ValueError:
        if not host.strip() or any(character.isspace() for character in host):
            return None
        url_host = host
    scheme = "wss" if "--tls" in arguments else "ws"
    return GatewayTarget(f"{scheme}://{url_host}:{port}{context_path}", "node_host")


def resolution_source(status: dict[str, Any], source_hint: str | None = None) -> str | None:
    rpc = status.get("rpc")
    if not isinstance(rpc, dict) or rpc.get("ok") is not True:
        return None
    url = rpc.get("url")
    if not isinstance(url, str):
        return None
    hostname = urlsplit(url).hostname
    if hostname is None:
        return None
    if source_hint in {"node_host", "tailscale"}:
        return source_hint
    if hostname.lower() == "localhost":
        return "local"
    try:
        return "local" if ipaddress.ip_address(hostname).is_loopback else "configured_remote"
    except ValueError:
        return "configured_remote"


def candidate_state_path(snapshot_path: Path) -> Path:
    return snapshot_path.with_name("gateway-candidates.json")




def tailscale_candidate(device: object) -> tuple[str, str, str] | None:
    if not isinstance(device, dict) or device.get("Online") is not True:
        return None
    device_id = device.get("ID")
    if not isinstance(device_id, str) or not device_id.strip():
        return None
    name = device.get("HostName")
    if not isinstance(name, str) or not name.strip():
        return None
    dns_name = device.get("DNSName")
    host = dns_name.rstrip(".") if isinstance(dns_name, str) else ""
    if not host:
        addresses = device.get("TailscaleIPs")
        host = addresses[0] if isinstance(addresses, list) and addresses else ""
    if not isinstance(host, str) or not host or any(character.isspace() for character in host):
        return None
    try:
        parsed_ip = ipaddress.ip_address(host)
        url_host = f"[{host}]" if parsed_ip.version == 6 else host
    except ValueError:
        if any(character in host for character in "/@?#:"):
            return None
        url_host = host
    return device_id.strip(), name.strip(), f"ws://{url_host}:{GATEWAY_PORT}"


def discover_tailscale_candidates(deadline_at: float) -> list[tuple[str, str, str]]:
    try:
        completed = run_command([*TAILSCALE_COMMAND, "status", "--json"], deadline_at)
    except (CollectionDeadlineExceeded, OSError):
        return []
    try:
        status = json.loads(completed.stdout) if completed.returncode == 0 else None
    except json.JSONDecodeError:
        status = None
    peers = status.get("Peer") if isinstance(status, dict) else None
    if not isinstance(peers, dict):
        return []
    candidates = [candidate for device in peers.values() if (candidate := tailscale_candidate(device))]
    return sorted(candidates, key=lambda candidate: candidate[1].casefold())




def retained_setup_candidates(previous: dict[str, Any] | None) -> list[dict[str, str]]:
    setup = previous.get("setup") if previous else None
    candidates = setup.get("candidates") if isinstance(setup, dict) else None
    if not isinstance(candidates, list):
        return []
    return [
        {"key": candidate["key"], "name": candidate["name"]}
        for candidate in candidates
        if (
            isinstance(candidate, dict)
            and isinstance(candidate.get("key"), str)
            and isinstance(candidate.get("name"), str)
        )
    ]


def setup_section(candidates: list[dict[str, str]], error: str | None = None) -> dict[str, Any]:
    setup: dict[str, Any] = {
        "candidates": candidates,
        "guidance": SETUP_GUIDANCE if candidates else NO_TAILSCALE_GUIDANCE,
    }
    if error:
        setup["error"] = error
    return setup


def build_setup_snapshot(
    previous: dict[str, Any] | None,
    refresh_interval: int,
    schema_version: int,
    setup: dict[str, Any],
    failure_kind: str | None = None,
) -> dict[str, Any]:
    snapshot = snapshot_envelope(
        schema_version,
        refresh_interval,
        "unresolved",
        "setup_required",
        None,
        0,
    )
    snapshot["fleet"] = {"available": False, "nodes": []}
    snapshot["agents"] = {"available": False, "items": []}
    snapshot["automations"] = {"available": False, "items": []}
    snapshot["bar"] = {"count": 0, "severity": "warning"}
    snapshot["setup"] = setup
    if failure_kind:
        snapshot["failureKind"] = failure_kind
    retained = last_known_metadata(previous)
    if retained is not None:
        snapshot["lastKnown"] = retained
    return snapshot


def setup_retry_snapshot(
    previous: dict[str, Any] | None,
    refresh_interval: int,
    schema_version: int,
    failure_kind: str,
    error: str,
) -> dict[str, Any]:
    return build_setup_snapshot(
        previous,
        refresh_interval,
        schema_version,
        setup_section(retained_setup_candidates(previous), error),
        failure_kind,
    )


def setup_required_snapshot(
    snapshot_path: Path,
    previous: dict[str, Any] | None,
    refresh_interval: int,
    deadline_at: float,
    schema_version: int,
    candidate_key_secret: bytes | None,
) -> dict[str, Any]:
    if candidate_key_secret is None:
        setup = setup_section(retained_setup_candidates(previous), KEY_SECRET_ERROR)
        setup["guidance"] = KEY_SECRET_ERROR
        return build_setup_snapshot(previous, refresh_interval, schema_version, setup)
    candidates = discover_tailscale_candidates(deadline_at)
    keyed_candidates = [
        (opaque_candidate_key(device_id, candidate_key_secret), name, url)
        for device_id, name, url in candidates
    ]
    public_candidates = [
        {"key": key, "name": name}
        for key, name, _ in keyed_candidates
    ]
    candidate_targets = {
        key: {"url": url}
        for key, _, url in keyed_candidates
    }
    atomic_write_snapshot(
        candidate_state_path(snapshot_path),
        {"schemaVersion": schema_version, "candidates": candidate_targets},
    )
    return build_setup_snapshot(
        previous,
        refresh_interval,
        schema_version,
        setup_section(public_candidates),
    )


def discover_node_host(openclaw_command: Sequence[str], deadline_at: float) -> GatewayTarget | None:
    completed = run_command([*openclaw_command, "node", "status", "--json"], deadline_at)
    if completed.returncode != 0:
        return None
    try:
        status = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    return node_host_target(status)




def selected_candidate(snapshot_path: Path, key: str, schema_version: int) -> GatewayTarget | None:
    state = load_snapshot(candidate_state_path(snapshot_path), schema_version)
    candidates = state.get("candidates") if state else None
    candidate = candidates.get(key) if isinstance(candidates, dict) else None
    url = candidate.get("url") if isinstance(candidate, dict) else None
    if not isinstance(url, str):
        return None
    return GatewayTarget(url, "tailscale")


def automatic_resolution_missing(completed: subprocess.CompletedProcess[str]) -> bool:
    try:
        status = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return False
    if not isinstance(status, dict):
        return False
    service = status.get("service")
    if isinstance(service, dict) and service.get("loaded") is True:
        return False
    rpc = status.get("rpc")
    url = rpc.get("url") if isinstance(rpc, dict) else None
    hostname = urlsplit(url).hostname if isinstance(url, str) else None
    if hostname is None:
        return False
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return hostname.lower() == "localhost"


def gateway_status_command(
    openclaw_command: Sequence[str],
    deadline_at: float,
    target: GatewayTarget | None = None,
    timeout_milliseconds: int = 10_000,
) -> subprocess.CompletedProcess[str]:
    timeout = max(1, min(timeout_milliseconds, int(seconds_until_deadline(deadline_at) * 1000)))
    command = [
        *openclaw_command,
        "gateway",
        "status",
        "--json",
        "--require-rpc",
        "--timeout",
        str(timeout),
    ]
    if target is not None:
        command.extend(["--url", target.url])
    return run_command(command, deadline_at)
