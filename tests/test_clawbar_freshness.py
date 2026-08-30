from __future__ import annotations

import json
import threading
import unittest

from scripts import clawbar_collect
from scripts.clawbar_commands import CollectionDeadlineExceeded
from tests.collector_fixture import CollectorFixture
from tests.fake_commands import FakeCommandSurface, gateway_unresolved, node_not_hosting, ok


class FreshnessCollectorTests(CollectorFixture, unittest.TestCase):
    def test_failures_retain_last_known_metadata_until_recovery(self) -> None:
        nodes = {
            "nodes": [
                {
                    "nodeId": "PRIVATE-NODE",
                    "displayName": "studio-ops",
                    "connected": False,
                }
            ]
        }
        healthy = self.collect(FakeCommandSurface.healthy(nodes_status=ok(nodes)))
        first_failure = self.collect(FakeCommandSurface.lost())
        second_failure = self.collect(FakeCommandSurface.lost())

        self.assertEqual(first_failure.snapshot["gateway"], {"state": "unstable"})
        self.assertEqual(first_failure.snapshot["consecutiveFailures"], 1)
        self.assertEqual(
            first_failure.snapshot["bar"],
            {"kind": "attention", "count": 1, "severity": "warning"},
        )
        self.assertEqual(
            first_failure.snapshot["lastKnown"]["fleet"],
            healthy.snapshot["fleet"],
        )
        self.assertEqual(
            first_failure.snapshot["lastKnown"]["observedAt"],
            healthy.snapshot["generatedAt"],
        )
        self.assertEqual(first_failure.snapshot["fleet"], {"available": False, "nodes": []})
        self.assertEqual(second_failure.snapshot["gateway"], {"state": "offline"})
        self.assertEqual(second_failure.snapshot["consecutiveFailures"], 2)
        self.assertEqual(second_failure.snapshot["lastKnown"], first_failure.snapshot["lastKnown"])

        recovered = self.collect(FakeCommandSurface.healthy(nodes_status=ok(nodes)))

        self.assertEqual(recovered.snapshot["gateway"], {"state": "healthy"})
        self.assertEqual(recovered.snapshot["consecutiveFailures"], 0)
        self.assertNotIn("lastKnown", recovered.snapshot)
        self.assertEqual(len(recovered.snapshot["fleet"]["nodes"]), 1)
        self.assertEqual(recovered.snapshot["fleet"]["nodes"][0]["name"], "studio-ops")

    def test_repeated_initial_failures_remain_no_data_yet(self) -> None:
        first = self.collect(FakeCommandSurface.lost())
        second = self.collect(FakeCommandSurface.lost())

        self.assertEqual(first.snapshot["gateway"], {"state": "no_data"})
        self.assertEqual(
            first.snapshot["bar"],
            {"kind": "none", "count": 0, "severity": "warning"},
        )
        self.assertEqual(second.snapshot["gateway"], {"state": "no_data"})
        self.assertEqual(
            second.snapshot["bar"],
            {"kind": "none", "count": 0, "severity": "warning"},
        )
        self.assertEqual(second.snapshot["consecutiveFailures"], 2)
        self.assertNotIn("lastKnown", second.snapshot)

    def test_partial_failure_does_not_carry_forward_section_values(self) -> None:
        nodes = {
            "nodes": [
                {
                    "nodeId": "PRIVATE-NODE",
                    "displayName": "Local",
                    "connected": True,
                }
            ]
        }
        healthy = self.collect(FakeCommandSurface.healthy(nodes_status=ok(nodes)))
        self.assertEqual(len(healthy.snapshot["fleet"]["nodes"]), 1)

        degraded = self.collect(FakeCommandSurface.healthy(nodes_status=CollectionDeadlineExceeded()))

        self.assertEqual(degraded.snapshot["gateway"], {"state": "degraded"})
        self.assertEqual(degraded.snapshot["fleet"], {"available": False, "nodes": []})
        self.assertEqual(degraded.snapshot["lastKnown"]["fleet"], healthy.snapshot["fleet"])

        failed = self.collect(FakeCommandSurface.lost())

        self.assertEqual(failed.snapshot["gateway"], {"state": "unstable"})
        self.assertEqual(failed.snapshot["lastKnown"]["fleet"], healthy.snapshot["fleet"])

    def test_degraded_agents_retain_complete_last_known_metadata(self) -> None:
        healthy = self.collect(FakeCommandSurface.healthy())

        degraded = self.collect(
            FakeCommandSurface.healthy(agents_list=CollectionDeadlineExceeded())
        )

        self.assertEqual(degraded.snapshot["gateway"], {"state": "degraded"})
        self.assertEqual(degraded.snapshot["agents"], {"available": False, "items": []})
        self.assertEqual(degraded.snapshot["lastKnown"]["fleet"], healthy.snapshot["fleet"])
        self.assertEqual(degraded.snapshot["lastKnown"]["agents"], healthy.snapshot["agents"])
        self.assertEqual(
            degraded.snapshot["lastKnown"]["automations"],
            healthy.snapshot["automations"],
        )

    def test_repeated_reads_observe_only_complete_atomic_snapshots(self) -> None:
        stop = threading.Event()
        errors: list[Exception] = []
        reads = 0

        def read_repeatedly() -> None:
            nonlocal reads
            while not stop.is_set():
                try:
                    value = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
                    self.assertIn(value["gateway"]["state"], {"healthy", "offline"})
                    self.assertEqual(len(value["fleet"]["nodes"]), 20)
                    reads += 1
                except Exception as error:
                    errors.append(error)
                    stop.set()

        def snapshot(state: str, generation: int) -> dict[str, object]:
            return {
                "schemaVersion": 1,
                "generatedAt": f"2026-08-21T00:00:{generation:02d}Z",
                "gateway": {"state": state},
                "fleet": {
                    "available": True,
                    "nodes": [{"key": f"node:{index}"} for index in range(20)],
                },
            }

        clawbar_collect.atomic_write_snapshot(self.snapshot_path, snapshot("healthy", 0))
        reader = threading.Thread(target=read_repeatedly)
        reader.start()
        try:
            for generation in range(1, 40):
                state = "healthy" if generation % 2 else "offline"
                clawbar_collect.atomic_write_snapshot(self.snapshot_path, snapshot(state, generation))
        finally:
            stop.set()
            reader.join()

        self.assertGreater(reads, 0)
        self.assertEqual(errors, [])

    def test_consecutive_failures_survive_collector_process_restart(self) -> None:
        healthy = self.run_external("local")
        first_failure = self.run_external(
            "local",
            environment_overrides={"FAKE_EXIT": "9", "FAKE_STDOUT": "connection broken"},
        )
        second_failure = self.run_external(
            "local",
            environment_overrides={"FAKE_EXIT": "9", "FAKE_STDOUT": "connection broken"},
        )

        self.assertEqual(healthy.returncode, clawbar_collect.ExitCode.OK, healthy.stderr)
        first_snapshot = json.loads(first_failure.stdout)
        second_snapshot = json.loads(second_failure.stdout)
        self.assertEqual(first_snapshot["gateway"], {"state": "unstable"})
        self.assertEqual(second_snapshot["gateway"], {"state": "offline"})
        self.assertEqual(second_snapshot["consecutiveFailures"], 2)
        self.assertEqual(
            second_snapshot["lastKnown"]["observedAt"],
            json.loads(healthy.stdout)["generatedAt"],
        )
    def test_missing_resolution_after_success_is_gateway_loss_not_setup(self) -> None:
        healthy = self.collect(FakeCommandSurface.healthy())
        unresolved = [
            FakeCommandSurface(gateway_status=gateway_unresolved(), node_status=node_not_hosting())
            for _ in range(2)
        ]

        first_failure = self.collect(unresolved[0])
        second_failure = self.collect(unresolved[1])

        self.assertEqual(healthy.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(first_failure.exit_code, clawbar_collect.ExitCode.COMMAND_FAILED)
        self.assertEqual(second_failure.exit_code, clawbar_collect.ExitCode.COMMAND_FAILED)
        self.assertEqual(first_failure.snapshot["gateway"], {"state": "unstable"})
        self.assertEqual(second_failure.snapshot["gateway"], {"state": "offline"})
        self.assertEqual(first_failure.snapshot["resolutionSource"], "local")
        for commands in unresolved:
            self.assertEqual(commands.asked("tailscale_status"), [])


if __name__ == "__main__":
    unittest.main()
