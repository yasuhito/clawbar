from __future__ import annotations

import json
import unittest

from scripts import clawbar_collect
from tests.collector_fixture import CollectorFixture
from tests.fake_commands import FakeCommandSurface, ok


class CollectionTests(CollectorFixture, unittest.TestCase):
    """Reduce Fleet and Registered Agent responses to Operational Metadata."""

    def test_distinguishes_empty_fleet_from_missing_gateway(self) -> None:
        result = self.collect(FakeCommandSurface.healthy())

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(result.snapshot["gateway"], {"state": "healthy"})
        self.assertEqual(result.snapshot["fleet"], {"available": True, "nodes": []})
        self.assertEqual(result.snapshot["agents"], {"available": True, "items": []})

    def test_sanitizes_registered_agents_and_task_results(self) -> None:
        private_sentinels = [
            "PRIVATE-HOST",
            "PRIVATE-IP",
            "PRIVATE-ACCOUNT",
            "PRIVATE-INSTRUCTION",
            "PRIVATE-DESTINATION",
            "PRIVATE-ERROR",
        ]
        nodes = {
            "nodes": [
                {
                    "displayName": "Local",
                    "connected": True,
                    "platform": "linux",
                    "modelIdentifier": "workstation",
                    "version": "2026.7.1",
                    "lastSeenAtMs": 1_787_280_000_000,
                    "nodeId": "PRIVATE-HOST",
                    "ip": "PRIVATE-IP",
                },
                {
                    "nodeId": "PRIVATE-HOST-2",
                    "displayName": "studio-ops",
                    "connected": True,
                },
            ]
        }
        agents = {
            "agents": [
                {"id": "planner", "model": "gpt-5", "workspace": "PRIVATE-HOST"},
                {"id": "builder", "accountId": "PRIVATE-ACCOUNT"},
                {"id": "observer"},
                {"id": "indexer"},
            ]
        }
        tasks = {
            "tasks": [
                {
                    "agentId": "planner",
                    "status": "running",
                    "updatedAt": 1_787_280_005_000,
                    "title": "PRIVATE-INSTRUCTION",
                },
                {
                    "agentId": "planner",
                    "status": "failed",
                    "endedAt": 1_787_280_004_000,
                    "error": "PRIVATE-ERROR",
                },
                {
                    "agentId": "builder",
                    "status": "queued",
                    "updatedAt": 1_787_280_003_000,
                    "destination": "PRIVATE-DESTINATION",
                },
                {
                    "agentId": "observer",
                    "status": "completed",
                    "endedAt": 1_787_280_002_000,
                },
            ]
        }

        result = self.collect(
            FakeCommandSurface.healthy(
                nodes_status=ok(nodes), agents_list=ok(agents), tasks_list=ok(tasks)
            )
        )

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
        snapshot = result.snapshot
        self.assertEqual(
            [node["name"] for node in snapshot["fleet"]["nodes"]],
            ["Local", "studio-ops"],
        )
        node_keys = [node["key"] for node in snapshot["fleet"]["nodes"]]
        self.assertEqual(len(set(node_keys)), 2)
        self.assertTrue(all(key.startswith("node:") for key in node_keys))
        by_name = {agent["name"]: agent for agent in snapshot["agents"]["items"]}
        self.assertNotIn("activity", by_name["planner"])
        self.assertEqual(by_name["planner"]["taskResult"]["state"], "failed")
        self.assertNotIn("activity", by_name["builder"])
        self.assertEqual(by_name["builder"]["taskResult"], {"state": "none"})
        self.assertNotIn("activity", by_name["observer"])
        self.assertEqual(by_name["observer"]["taskResult"]["state"], "succeeded")
        self.assertNotIn("activity", by_name["indexer"])
        self.assertEqual(by_name["indexer"]["taskResult"], {"state": "none"})
        self.assertEqual(snapshot["gateway"], {"state": "healthy"})
        serialized = json.dumps(snapshot)
        for sentinel in private_sentinels:
            self.assertNotIn(sentinel, serialized)

    def test_same_named_node_registrations_collapse_to_freshest_connected_node(
        self,
    ) -> None:
        first_nodes = {
            "nodes": [
                {
                    "nodeId": "PRIVATE-NODE-A",
                    "displayName": "MacBook Pro",
                    "connected": True,
                    "lastSeenAtMs": 1_000,
                    "platform": "macOS 26.5.1",
                    "modelIdentifier": "MacBookPro18,3",
                    "version": "2026.1.8",
                },
                {
                    "nodeId": "PRIVATE-NODE-B",
                    "displayName": "MacBook Pro",
                    "connected": True,
                    "lastSeenAtMs": 2_000,
                    "platform": "macos",
                    "version": "2026.7.1",
                },
                {
                    "nodeId": "PRIVATE-NODE-LEGACY",
                    "displayName": "MacBook Pro",
                    "connected": False,
                    "version": "2026.10.0",
                },
                {
                    "nodeId": "PRIVATE-STUDIO-CURRENT",
                    "displayName": "Studio",
                    "connected": True,
                    "lastSeenAtMs": 3_000,
                    "platform": "macOS 27.0",
                },
                {
                    "nodeId": "PRIVATE-STUDIO-LEGACY",
                    "displayName": "Studio",
                    "connected": False,
                    "platform": "macOS 26.5.1",
                },
            ]
        }
        second_nodes = {"nodes": list(reversed(first_nodes["nodes"]))}
        replacement_nodes = {
            "nodes": [
                {
                    "nodeId": "PRIVATE-NODE-C",
                    "displayName": "MacBook Pro",
                    "connected": True,
                    "lastSeenAtMs": 3_000,
                    "version": "replacement",
                }
            ]
        }

        first = self.collect(FakeCommandSurface.healthy(nodes_status=ok(first_nodes)))
        second = self.collect(FakeCommandSurface.healthy(nodes_status=ok(second_nodes)))
        replacement = self.collect(
            FakeCommandSurface.healthy(nodes_status=ok(replacement_nodes))
        )
        first_fleet = first.snapshot["fleet"]["nodes"]
        second_fleet = second.snapshot["fleet"]["nodes"]
        replacement_fleet = replacement.snapshot["fleet"]["nodes"]

        for result in (first, second, replacement):
            self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(
            {node["name"]: node for node in first_fleet},
            {node["name"]: node for node in second_fleet},
        )
        self.assertEqual(len(first_fleet), 2)
        self.assertEqual(first_fleet[0]["state"], "healthy")
        self.assertEqual(first_fleet[0]["platform"], "macOS 26.5.1")
        self.assertEqual(first_fleet[0]["model"], "MacBookPro18,3")
        self.assertEqual(first_fleet[0]["version"], "2026.7.1")
        self.assertEqual(replacement_fleet[0]["version"], "replacement")
        self.assertEqual(replacement_fleet[0]["key"], first_fleet[0]["key"])
        serialized = json.dumps([first.snapshot, second.snapshot, replacement.snapshot])
        self.assertNotIn("PRIVATE-NODE", serialized)
        studio = next(node for node in first_fleet if node["name"] == "Studio")
        self.assertEqual(studio["platform"], "macOS 27.0")

    def test_fresh_registration_after_first_hundred_duplicates_is_retained(
        self,
    ) -> None:
        nodes = [
            {
                "nodeId": f"PRIVATE-NODE-{index}",
                "displayName": "MacBook Pro",
                "connected": False,
            }
            for index in range(100)
        ]
        nodes.append(
            {
                "nodeId": "PRIVATE-NODE-CURRENT",
                "displayName": "MacBook Pro",
                "connected": True,
                "lastSeenAtMs": 3_000,
                "version": "current",
            }
        )

        result = self.collect(
            FakeCommandSurface.healthy(nodes_status=ok({"nodes": nodes}))
        )
        fleet = result.snapshot["fleet"]["nodes"]

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(len(fleet), 1)
        self.assertEqual(fleet[0]["state"], "healthy")
        self.assertEqual(fleet[0]["version"], "current")

    def test_node_keys_stay_stable_without_runtime_directory(self) -> None:
        nodes = {
            "nodes": [
                {"nodeId": "PRIVATE-NODE", "displayName": "Local", "connected": True}
            ]
        }
        environment = {
            "XDG_RUNTIME_DIR": "",
            "XDG_STATE_HOME": str(self.root / "state"),
        }

        first = self.collect(
            FakeCommandSurface.healthy(nodes_status=ok(nodes)),
            secret=None,
            **environment,
        )
        second = self.collect(
            FakeCommandSurface.healthy(nodes_status=ok(nodes)),
            secret=None,
            **environment,
        )

        first_node = first.snapshot["fleet"]["nodes"][0]
        second_node = second.snapshot["fleet"]["nodes"][0]
        self.assertEqual(first.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(second.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(first_node["key"], second_node["key"])
        self.assertTrue(first_node["key"].startswith("node:"))
        self.assertNotIn("PRIVATE-NODE", json.dumps([first.snapshot, second.snapshot]))

    def test_invalid_node_key_secret_makes_fleet_unavailable(self) -> None:
        secret_path = self.root / "runtime" / "clawbar" / "node-key-secret"
        secret_path.parent.mkdir(parents=True)
        secret_path.write_bytes(b"invalid")
        nodes = {
            "nodes": [
                {"nodeId": "PRIVATE-NODE", "displayName": "Local", "connected": True}
            ]
        }

        result = self.collect(
            FakeCommandSurface.healthy(nodes_status=ok(nodes)), secret=None
        )

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(result.snapshot["gateway"], {"state": "degraded"})
        self.assertEqual(result.snapshot["fleet"], {"available": False, "nodes": []})
        self.assertNotIn("PRIVATE-NODE", json.dumps(result.snapshot))

    def test_node_without_private_identity_makes_fleet_unavailable(self) -> None:
        nodes = {"nodes": [{"displayName": "Local", "connected": True}]}

        result = self.collect(FakeCommandSurface.healthy(nodes_status=ok(nodes)))

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(result.snapshot["gateway"], {"state": "degraded"})
        self.assertEqual(result.snapshot["fleet"], {"available": False, "nodes": []})
