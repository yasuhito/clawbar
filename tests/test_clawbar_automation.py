from __future__ import annotations

import json
import unittest

from scripts import clawbar_collect
from tests.collector_fixture import CollectorFixture


class AutomationCollectorTests(CollectorFixture, unittest.TestCase):
    @staticmethod
    def automation_surface(automation_id: str = "stable-automation-id") -> dict[str, object]:
        return {
            "jobs": [{
                "id": automation_id,
                "name": "Investigate",
                "enabled": True,
                "schedule": {"kind": "cron"},
                "state": {},
            }]
        }

    def test_executable_sanitizes_orders_and_aggregates_automations(self) -> None:
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

        result = self.run_external(
            "local",
            environment_overrides={
                "FAKE_AUTOMATIONS": json.dumps(automations),
                "FAKE_NODES": json.dumps(nodes),
            },
        )

        self.assertEqual(result.returncode, clawbar_collect.ExitCode.OK, result.stderr)
        snapshot = json.loads(result.stdout)
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
        for sentinel in private_sentinels:
            self.assertNotIn(sentinel, result.stdout)

    def test_automation_empty_unavailable_and_limit_states_are_explicit(self) -> None:
        scenarios = [
            (
                "empty",
                {"FAKE_AUTOMATIONS": json.dumps({"jobs": []})},
                {"available": True, "items": []},
                {"state": "healthy"},
            ),
            (
                "failed",
                {"FAKE_AUTOMATIONS_EXIT": "9"},
                {"available": False, "items": [], "reason": "unavailable"},
                {"state": "degraded"},
            ),
            (
                "too-many",
                {
                    "FAKE_AUTOMATIONS": json.dumps({
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
                    })
                },
                {"available": False, "items": [], "reason": "more_than_500"},
                {"state": "degraded"},
            ),
        ]
        for name, overrides, expected_automations, expected_gateway in scenarios:
            with self.subTest(name=name):
                overrides["XDG_STATE_HOME"] = str(self.root / f"{name}-state")
                result = self.run_external("local", environment_overrides=overrides)
                snapshot = json.loads(result.stdout)

                self.assertEqual(result.returncode, clawbar_collect.ExitCode.OK, result.stderr)
                self.assertEqual(snapshot["automations"], expected_automations)
                self.assertEqual(snapshot["gateway"], expected_gateway)
                expected_bar = (
                    {"count": 0, "kind": "working_agents", "severity": "healthy"}
                    if name == "empty"
                    else {"count": 1, "kind": "attention", "severity": "warning"}
                )
                self.assertEqual(snapshot["bar"], expected_bar)

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
            "0": {"jobs": jobs[:200], "total": 450, "hasMore": True, "nextOffset": 200},
            "200": {"jobs": jobs[200:400], "total": 450, "hasMore": True, "nextOffset": 400},
            "400": {"jobs": jobs[400:], "total": 450, "hasMore": False},
        }

        result = self.run_external(
            "local",
            environment_overrides={"FAKE_AUTOMATION_PAGES": json.dumps(pages)},
        )

        self.assertEqual(result.returncode, clawbar_collect.ExitCode.OK, result.stderr)
        snapshot = json.loads(result.stdout)
        self.assertEqual(len(snapshot["automations"]["items"]), 450)
        cron_calls = [call for call in self.read_calls() if call[:3] == ["gateway", "call", "cron.list"]]
        params = [json.loads(call[call.index("--params") + 1]) for call in cron_calls]
        self.assertEqual(
            params,
            [
                {"includeDisabled": True, "limit": 200, "offset": 0},
                {"includeDisabled": True, "limit": 200, "offset": 200},
                {"includeDisabled": True, "limit": 101, "offset": 400},
            ],
        )

    def test_healthy_bar_counts_working_agents(self) -> None:
        agents = {"agents": [{"id": "planner"}]}
        tasks = {"tasks": [{"agentId": "planner", "status": "running"}]}

        result = self.run_external(
            "local",
            environment_overrides={"FAKE_AGENTS": json.dumps(agents), "FAKE_TASKS": json.dumps(tasks)},
        )

        snapshot = json.loads(result.stdout)
        self.assertEqual(snapshot["bar"], {"count": 1, "kind": "working_agents", "severity": "healthy"})


if __name__ == "__main__":
    unittest.main()
