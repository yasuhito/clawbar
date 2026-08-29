from __future__ import annotations

import json
import unittest

from scripts import clawbar_collect
from tests.collector_fixture import CollectorFixture
from tests.fake_commands import FakeCommandSurface, failed, ok


class AutomationCollectorTests(CollectorFixture, unittest.TestCase):
    def test_collection_sanitizes_orders_and_aggregates_automations(self) -> None:
        private_sentinels = [
            "PRIVATE-PAYLOAD",
            "PRIVATE-DESTINATION",
            "PRIVATE-ACCOUNT",
            "PRIVATE-DELIVERY",
            "PRIVATE-ERROR",
        ]
        automations = {
            "jobs": [
                {
                    "id": "disabled-id",
                    "name": "Zebra disabled",
                    "enabled": False,
                    "schedule": {"kind": "cron", "expr": "* * * * *"},
                    "state": {"lastRunAtMs": 7_000, "lastRunStatus": "error", "consecutiveErrors": 9},
                },
                {
                    "id": "event-id",
                    "name": "Event watcher",
                    "enabled": True,
                    "schedule": {"kind": "on-exit", "command": "PRIVATE-PAYLOAD"},
                    "state": {},
                },
                {
                    "id": "complete-id",
                    "name": "Completed once",
                    "enabled": True,
                    "schedule": {"kind": "at", "at": "2026-08-22T00:00:00Z"},
                    "state": {"lastRunAtMs": 6_000, "lastRunStatus": "ok"},
                },
                {
                    "id": "success-id",
                    "name": "Successful",
                    "enabled": True,
                    "schedule": {"kind": "cron", "expr": "0 * * * *"},
                    "state": {"nextRunAtMs": 3_000, "lastRunAtMs": 2_000, "lastRunStatus": "ok"},
                    "payload": {"message": "PRIVATE-PAYLOAD"},
                    "delivery": {"to": "PRIVATE-DESTINATION", "account": "PRIVATE-ACCOUNT"},
                },
                {
                    "id": "skipped-id",
                    "name": "Skipped",
                    "enabled": True,
                    "schedule": {"kind": "every", "everyMs": 60_000},
                    "state": {"nextRunAtMs": 2_000, "lastRunAtMs": 1_000, "lastRunStatus": "skipped"},
                },
                {
                    "id": "new-id",
                    "name": "Never run",
                    "enabled": True,
                    "schedule": {"kind": "cron", "expr": "*/5 * * * *"},
                    "state": {"nextRunAtMs": 1_000},
                },
                {
                    "id": "failure-id",
                    "name": "Failed",
                    "enabled": True,
                    "schedule": {"kind": "cron", "expr": "0 0 * * *"},
                    "state": {
                        "nextRunAtMs": 4_000,
                        "lastRunAtMs": 3_500,
                        "lastRunStatus": "error",
                        "consecutiveErrors": 3,
                        "lastError": "PRIVATE-ERROR",
                        "lastDeliveryError": "PRIVATE-DELIVERY",
                    },
                },
            ]
        }
        nodes = {"nodes": [{"nodeId": "offline-node", "displayName": "Offline", "connected": False}]}

        result = self.collect(
            FakeCommandSurface.healthy(cron_list=ok(automations), nodes_status=ok(nodes))
        )

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
        snapshot = result.snapshot
        items = snapshot["automations"]["items"]
        self.assertEqual(
            [item["name"] for item in items],
            ["Failed", "Never run", "Skipped", "Successful", "Completed once", "Event watcher", "Zebra disabled"],
        )
        self.assertEqual(
            set(items[0]),
            {"id", "name", "enabled", "kind", "nextRunAt", "lastRunAt", "lastResult", "consecutiveFailures"},
        )
        self.assertEqual(items[0]["lastResult"], "error")
        self.assertEqual(items[0]["consecutiveFailures"], 3)
        self.assertEqual(items[1]["lastResult"], "none")
        self.assertEqual(items[2]["lastResult"], "skipped")
        self.assertEqual(items[4]["kind"], "at")
        self.assertEqual(items[5]["kind"], "on-exit")
        self.assertEqual(items[6]["enabled"], False)
        self.assertEqual(snapshot["gateway"], {"state": "healthy"})
        self.assertEqual(snapshot["bar"], {"count": 1, "kind": "attention", "severity": "critical"})
        published = json.dumps(snapshot)
        for sentinel in private_sentinels:
            self.assertNotIn(sentinel, published)

    def test_automation_empty_unavailable_and_limit_states_are_explicit(self) -> None:
        too_many = {
            "jobs": [
                {
                    "id": f"automation-{index}",
                    "name": f"Automation {index}",
                    "enabled": True,
                    "schedule": {"kind": "cron"},
                    "state": {"lastRunStatus": "error"},
                }
                for index in range(501)
            ]
        }
        scenarios = [
            ("empty", ok({"jobs": []}), {"available": True, "items": []}, {"state": "healthy"}),
            ("failed", failed(9), {"available": False, "items": [], "reason": "unavailable"}, {"state": "degraded"}),
            ("too-many", ok(too_many), {"available": False, "items": [], "reason": "more_than_500"}, {"state": "degraded"}),
        ]
        for name, cron_answer, expected_automations, expected_gateway in scenarios:
            with self.subTest(name=name):
                result = self.collect(
                    FakeCommandSurface.healthy(cron_list=cron_answer),
                    snapshot_path=self.root / f"{name}-state" / "snapshot.json",
                )

                self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
                self.assertEqual(result.snapshot["automations"], expected_automations)
                self.assertEqual(result.snapshot["gateway"], expected_gateway)
                expected_bar = (
                    {"count": 0, "kind": "none", "severity": "healthy"}
                    if name == "empty"
                    else {"count": 1, "kind": "attention", "severity": "warning"}
                )
                self.assertEqual(result.snapshot["bar"], expected_bar)

    def test_automation_collection_pages_within_supported_limit(self) -> None:
        jobs = [
            {
                "id": f"automation-{index}",
                "name": f"Automation {index:03d}",
                "enabled": True,
                "schedule": {"kind": "cron"},
                "state": {},
            }
            for index in range(450)
        ]
        pages = {
            0: {"jobs": jobs[:200], "total": 450, "hasMore": True, "nextOffset": 200},
            200: {"jobs": jobs[200:400], "total": 450, "hasMore": True, "nextOffset": 400},
            400: {"jobs": jobs[400:], "total": 450, "hasMore": False},
        }
        commands = FakeCommandSurface.healthy(cron_list=lambda url, params: ok(pages[params["offset"]]))

        result = self.collect(commands)

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(len(result.snapshot["automations"]["items"]), 450)
        self.assertEqual(
            [call["params"] for call in commands.asked("cron_list")],
            [
                {"includeDisabled": True, "limit": 200, "offset": 0},
                {"includeDisabled": True, "limit": 200, "offset": 200},
                {"includeDisabled": True, "limit": 101, "offset": 400},
            ],
        )

    def test_healthy_bar_does_not_count_running_agent_tasks(self) -> None:
        commands = FakeCommandSurface.healthy(
            agents_list=ok({"agents": [{"id": "planner"}]}),
            tasks_list=ok({"tasks": [{"agentId": "planner", "status": "running"}]}),
        )

        result = self.collect(commands)

        self.assertEqual(result.snapshot["bar"], {"count": 0, "kind": "none", "severity": "healthy"})


if __name__ == "__main__":
    unittest.main()
