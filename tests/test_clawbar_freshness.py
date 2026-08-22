from __future__ import annotations

import json
import threading
import unittest

from scripts import clawbar_collect
from tests.collector_fixture import CollectorFixture


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
        with self.fake_environment(FAKE_NODES=json.dumps(nodes)):
            healthy = self.run_collector()
        first_failure = self.run_collector(stdout="connection broken", exit_code=9)
        second_failure = self.run_collector(stdout="connection broken", exit_code=9)

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

        with self.fake_environment(FAKE_NODES=json.dumps(nodes)):
            recovered = self.run_collector()

        self.assertEqual(recovered.snapshot["gateway"], {"state": "healthy"})
        self.assertEqual(recovered.snapshot["consecutiveFailures"], 0)
        self.assertNotIn("lastKnown", recovered.snapshot)
        self.assertEqual(len(recovered.snapshot["fleet"]["nodes"]), 1)
        self.assertEqual(recovered.snapshot["fleet"]["nodes"][0]["name"], "studio-ops")

    def test_repeated_initial_failures_remain_no_data_yet(self) -> None:
        first = self.run_collector(stdout="connection broken", exit_code=9)
        second = self.run_collector(stdout="connection broken", exit_code=9)

        self.assertEqual(first.snapshot["gateway"], {"state": "no_data"})
        self.assertEqual(second.snapshot["gateway"], {"state": "no_data"})
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
        with self.fake_environment(FAKE_NODES=json.dumps(nodes)):
            healthy = self.run_collector()
        self.assertEqual(len(healthy.snapshot["fleet"]["nodes"]), 1)

        degraded = self.run_collector(nodes_delay=0.3, deadline=0.1)

        self.assertEqual(degraded.snapshot["gateway"], {"state": "degraded"})
        self.assertEqual(degraded.snapshot["fleet"], {"available": False, "nodes": []})
        self.assertEqual(degraded.snapshot["lastKnown"]["fleet"], healthy.snapshot["fleet"])

        failed = self.run_collector(stdout="connection broken", exit_code=9)

        self.assertEqual(failed.snapshot["gateway"], {"state": "unstable"})
        self.assertEqual(failed.snapshot["lastKnown"]["fleet"], healthy.snapshot["fleet"])

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
        healthy = self.run_external("local")
        self.call_log_path.unlink(missing_ok=True)

        first_failure = self.run_external("unresolved")
        second_failure = self.run_external("unresolved")

        self.assertEqual(healthy.returncode, clawbar_collect.ExitCode.OK, healthy.stderr)
        self.assertEqual(first_failure.returncode, clawbar_collect.ExitCode.COMMAND_FAILED)
        self.assertEqual(second_failure.returncode, clawbar_collect.ExitCode.COMMAND_FAILED)
        first_snapshot = json.loads(first_failure.stdout)
        second_snapshot = json.loads(second_failure.stdout)
        self.assertEqual(first_snapshot["gateway"], {"state": "unstable"})
        self.assertEqual(second_snapshot["gateway"], {"state": "offline"})
        self.assertEqual(first_snapshot["resolutionSource"], "local")
        self.assertNotIn(["tailscale", "status", "--json"], self.read_calls())



if __name__ == "__main__":
    unittest.main()
