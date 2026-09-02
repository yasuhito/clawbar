"""Command-line entry point for the bounded Clawbar collector."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

if __package__:
    from .clawbar_snapshot import read_bounded_regular_file
else:
    from clawbar_snapshot import read_bounded_regular_file


def _collector_module():
    if __package__:
        from . import clawbar_collect
    else:
        import clawbar_collect
    return clawbar_collect


def default_snapshot_path() -> Path:
    state_home = os.environ.get("XDG_STATE_HOME")
    base = Path(state_home) if state_home else Path.home() / ".local" / "state"
    return base / "clawbar" / "snapshot.json"


def developer_demo_active() -> bool:
    runtime_directory = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime_directory:
        return False
    try:
        marker = Path(runtime_directory) / "clawbar" / "demo-active"
        return read_bounded_regular_file(marker, 16).decode("utf-8").strip() == "1"
    except (OSError, UnicodeDecodeError):
        return False


def parse_refresh_interval(value: str) -> int:
    collector = _collector_module()
    try:
        return collector.validate_refresh_interval(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "refresh interval must be an integer from 15 through 300 seconds"
        ) from error


def print_bounded_text_file(path: Path) -> int:
    collector = _collector_module()
    try:
        content = read_bounded_regular_file(path).decode("utf-8")
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        return int(collector.ExitCode.COMMAND_FAILED)
    sys.stdout.write(content)
    return int(collector.ExitCode.OK)


def build_parser() -> argparse.ArgumentParser:
    collector = _collector_module()
    parser = argparse.ArgumentParser(
        description=(
            "Collect one structured OpenClaw Gateway status into Clawbar's cache. "
            f"The whole collection exits within {int(collector.COLLECTION_DEADLINE_SECONDS)} seconds."
        )
    )
    parser.add_argument(
        "--read-cache",
        action="store_true",
        help="print the bounded regular snapshot cache without collecting",
    )
    parser.add_argument(
        "--read-theme-colors",
        type=Path,
        metavar="PATH",
        help="print one bounded regular UTF-8 theme colors file without collecting",
    )
    parser.add_argument(
        "--refresh-interval",
        default=collector.DEFAULT_REFRESH_INTERVAL_SECONDS,
        type=parse_refresh_interval,
        metavar="SECONDS",
    )
    parser.add_argument(
        "--verify-candidate",
        metavar="CANDIDATE_KEY",
        help="verify one enumerated Tailscale candidate and collect from it",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    collector = _collector_module()
    if __package__:
        from .clawbar_commands import SubprocessCommandSurface
    else:
        from clawbar_commands import SubprocessCommandSurface

    arguments = build_parser().parse_args(argv)
    snapshot_path = default_snapshot_path()
    if arguments.read_theme_colors is not None:
        return print_bounded_text_file(arguments.read_theme_colors)
    if arguments.read_cache:
        snapshot = collector.load_previous_snapshot(snapshot_path)
        if snapshot is None:
            return int(collector.ExitCode.COMMAND_FAILED)
        json.dump(snapshot, sys.stdout, separators=(",", ":"), sort_keys=True)
        sys.stdout.write("\n")
        return int(collector.ExitCode.OK)
    if developer_demo_active():
        snapshot = collector.load_previous_snapshot(snapshot_path)
        if snapshot is not None:
            json.dump(snapshot, sys.stdout, separators=(",", ":"), sort_keys=True)
            sys.stdout.write("\n")
        return int(collector.ExitCode.OK)
    result = collector.collect_gateway(
        snapshot_path,
        arguments.refresh_interval,
        commands=SubprocessCommandSurface(),
        candidate_key=arguments.verify_candidate,
    )
    json.dump(result.snapshot, sys.stdout, separators=(",", ":"), sort_keys=True)
    sys.stdout.write("\n")
    return int(result.exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
