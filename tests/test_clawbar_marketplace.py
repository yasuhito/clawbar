from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ID = "io.github.yasuhito.clawbar"


DEMO_SCENARIOS = (
    "setup-required",
    "healthy",
    "registered-agents",
    "unstable-gateway",
    "offline-gateway",
    "degraded-gateway",
    "configuration-error",
    "automation-failure",
    "stale-snapshot",
    "empty-fleet",
    "grouped-incidents",
    "recovery",
)


class MarketplaceContractTest(unittest.TestCase):
    def test_qml_treats_all_display_text_as_plain_text(self) -> None:
        for path in ROOT.glob("*.qml"):
            source = path.read_text(encoding="utf-8")
            text_controls = source.count("Text {")
            if text_controls == 0:
                continue
            with self.subTest(path=path.name):
                self.assertEqual(
                    source.count("textFormat: Text.PlainText"),
                    text_controls,
                    f"every Text control in {path.name} must reject rich-text interpretation",
                )

    def test_qml_reads_the_snapshot_through_the_bounded_collector_interface(
        self,
    ) -> None:
        widget = (ROOT / "Clawbar.qml").read_text(encoding="utf-8")

        self.assertNotIn('command: ["cat", root.snapshotPath]', widget)
        self.assertIn('"--read-cache"', widget)

    def test_qml_reads_theme_colors_through_the_bounded_collector_interface(
        self,
    ) -> None:
        widget = (ROOT / "Clawbar.qml").read_text(encoding="utf-8")

        self.assertNotIn("FileView", widget)
        self.assertIn('"--read-theme-colors"', widget)

    def test_manifest_declares_widget_and_scheduler_service(self) -> None:
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["id"], PLUGIN_ID)
        self.assertEqual(
            manifest["description"],
            "A read-only OpenClaw fleet status view for the Omarchy bar.",
        )
        self.assertEqual(set(manifest["kinds"]), {"bar-widget", "service"})
        self.assertEqual(manifest["entryPoints"]["barWidget"], "Clawbar.qml")
        self.assertEqual(manifest["entryPoints"]["service"], "ClawbarService.qml")
        self.assertEqual(manifest["barWidget"]["defaultSection"], "right")
        for entry_point in manifest["entryPoints"].values():
            self.assertTrue((ROOT / entry_point).is_file())
        self.assertTrue((ROOT / "LICENSE").is_file())

    def test_bar_icon_keeps_color_only_signal(self) -> None:
        widget = (ROOT / "Clawbar.qml").read_text(encoding="utf-8")

        self.assertIn("color: root.barSignalColor", widget)
        self.assertNotIn("String(root.barCount)", widget)

    def test_bar_icon_uses_openclaw_right_claw_with_contextual_motion(self) -> None:
        widget = (ROOT / "Clawbar.qml").read_text(encoding="utf-8")
        mark = (ROOT / "ClawMark.qml").read_text(encoding="utf-8")
        service = (ROOT / "ClawbarService.qml").read_text(encoding="utf-8")

        self.assertIn(
            "M8.2 10 A5.2 5.2 0 1 0 8.2 20.4",
            mark,
        )
        self.assertIn("M5.6 12.2 C5.2 5.6 10.4 1.4 15.6 2", mark)
        self.assertIn("icons-tools.ts", mark)
        self.assertIn("property real jawAngle: -10", mark)
        self.assertIn("origin.x: 8.6", mark)
        self.assertIn("origin.y: 11", mark)
        self.assertIn("property bool animated: false", mark)
        self.assertIn("loops: Animation.Infinite", mark)
        self.assertIn('property: "jawAngle"\n      to: -26\n      duration: 96', mark)
        self.assertIn('property: "jawAngle"\n      to: 4\n      duration: 144', mark)
        self.assertIn("PauseAnimation {\n      duration: 1392\n    }", mark)
        self.assertIn("button.tooltipHovered", widget)
        self.assertIn("collectorService.collecting", widget)
        self.assertIn("readonly property bool collecting:", service)

    def test_manual_refresh_feedback_is_distinct_from_scheduled_collection(
        self,
    ) -> None:
        widget = (ROOT / "Clawbar.qml").read_text(encoding="utf-8")
        service = (ROOT / "ClawbarService.qml").read_text(encoding="utf-8")

        self.assertIn('property string refreshFeedback: "idle"', widget)
        self.assertIn("interval: 6000", widget)
        self.assertIn("collectorService.requestCollection(true)", widget)
        self.assertIn('refreshFeedback = "failed"', widget)
        self.assertIn("function onCollectionFinished(interactive, succeeded)", widget)
        self.assertIn("property bool collectorInteractive: false", service)
        self.assertIn("property bool refreshPendingInteractive: false", service)
        self.assertIn("readonly property bool interactiveRefreshing:", service)
        self.assertIn(
            "signal collectionFinished(bool interactive, bool succeeded)", service
        )
        self.assertIn("function requestCollection(interactive)", service)
        self.assertIn("root.requestCollection(false)", service)
        self.assertIn("root.startCollection(pendingInteractive)", service)

    def test_panel_omits_the_rejected_shortcut_footer(self) -> None:
        panel = (ROOT / "ClawbarPanel.qml").read_text(encoding="utf-8")

        self.assertNotIn("j/k · arrows", panel)

    def test_panel_omits_empty_agents_section(self) -> None:
        panel_model = (ROOT / "ClawbarPanelModel.js").read_text(encoding="utf-8")

        self.assertIn("data.agents.length > 0 || agentsUnavailable", panel_model)

    def test_panel_omits_the_obsolete_fleet_rail(self) -> None:
        panel = (ROOT / "ClawbarPanel.qml").read_text(encoding="utf-8")

        self.assertNotIn("id: fleetRail", panel)

    def test_panel_pins_gateway_header_above_the_scrolling_rows(self) -> None:
        panel = (ROOT / "ClawbarPanel.qml").read_text(encoding="utf-8")
        header = (ROOT / "PanelHeader.qml").read_text(encoding="utf-8")
        header_start = panel.index("id: panelHeader")
        flick_start = panel.index("id: panelFlick")
        content_start = panel.index("id: contentColumn")

        self.assertLess(header_start, flick_start)
        self.assertLess(flick_start, content_start)
        self.assertIn('text: "OpenClaw"', header)
        self.assertNotIn('text: "OpenClaw"', panel[content_start:])
        self.assertIn("anchors.top: panelHeader.bottom", panel)
        self.assertIn(
            "panelHeader.height + Style.space(4) + contentColumn.implicitHeight",
            panel,
        )

    def test_scroll_indicator_reflects_scrollability_position_and_activity(
        self,
    ) -> None:
        panel = (ROOT / "ClawbarPanel.qml").read_text(encoding="utf-8")

        self.assertIn("id: scrollIndicator", panel)
        self.assertIn(
            "visible: panelFlick.contentHeight > panelFlick.height + 1",
            panel,
        )
        self.assertIn("readonly property real scrollProgress", panel)
        self.assertIn(
            "panelFlick.contentY / (panelFlick.contentHeight - panelFlick.height)",
            panel,
        )
        self.assertIn(
            "panelFlick.height * Math.min(1, panelFlick.height / panelFlick.contentHeight)",
            panel,
        )
        self.assertIn("id: scrollIndicatorActivity", panel)
        self.assertIn(
            "if (interactive)\n          scrollIndicatorActivity.restart();", panel
        )
        self.assertIn("Behavior on opacity", panel)
        self.assertIn("width: panelFlick.width - Style.space(8)", panel)

    def test_operational_details_share_short_reveal_motion(self) -> None:
        panel = (ROOT / "ClawbarPanel.qml").read_text(encoding="utf-8")
        reveal = (ROOT / "DetailReveal.qml").read_text(encoding="utf-8")
        section = (ROOT / "RowSection.qml").read_text(encoding="utf-8")

        self.assertIn("DETAIL REVEAL STORYBOARD", panel)
        self.assertIn("property bool detailMotionEnabled: true", panel)
        self.assertIn("readonly property int detailFadeDuration: 120", panel)
        self.assertIn("readonly property int detailExpandDuration: 180", panel)
        # One shared reveal implementation replaces the per-kind copies.
        self.assertEqual(reveal.count("Behavior on height"), 1)
        self.assertEqual(reveal.count("Behavior on opacity"), 1)
        self.assertNotIn("Behavior on height", section)
        self.assertNotIn("Behavior on height", panel)
        self.assertIn("height: summaryArea.height + detailReveal.height", section)
        self.assertIn("expanded: rowRoot.selected", section)
        self.assertIn("Accessible.ignored: !expanded", reveal)
        self.assertEqual(section.count("DetailCard {"), 1)
        self.assertIn("sourceComponent: detailCardComponent", section)
        self.assertIn("signal selectionGeometryChanged\n", section)
        self.assertIn("onSelectionGeometryChanged", panel)

    def test_operational_row_detail_uses_declarative_bindings(self) -> None:
        section = (ROOT / "RowSection.qml").read_text(encoding="utf-8")

        self.assertNotIn("onLoaded:", section)
        self.assertNotIn("item.vm =", section)
        self.assertIn("vm: rowRoot.modelData", section)
        self.assertIn("palette: root.palette", section)
        self.assertIn("nowMs: root.nowMs", section)

    def test_operational_row_detail_loader_skips_collapsed_and_empty_rows(self) -> None:
        section = (ROOT / "RowSection.qml").read_text(encoding="utf-8")

        self.assertIn("Loader {", section)
        self.assertIn(
            "active: rowRoot.modelData.detail.length > 0",
            section,
        )
        self.assertIn("&& (rowRoot.selected || detailReveal.height > 0)", section)
        self.assertIn(
            "contentHeight: cardLoader.active && cardLoader.item",
            section,
        )

    def test_automation_selection_has_no_run_history_action(self) -> None:
        sources = "\n".join(
            (ROOT / path).read_text(encoding="utf-8")
            for path in (
                "Clawbar.qml",
                "ClawbarPanel.qml",
                "RowSection.qml",
                "DetailCard.qml",
            )
        )

        collector = (ROOT / "scripts" / "clawbar_collect.py").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("View run history", sources)
        self.assertNotIn("automationHistory", sources)
        self.assertNotIn("historyLauncher", sources)
        self.assertNotIn("--automation-history", collector)
        self.assertNotIn("open_automation_history", collector)

    def test_registered_agents_use_a_static_green_dot_without_activity_claims(
        self,
    ) -> None:
        panel = (ROOT / "ClawbarPanel.qml").read_text(encoding="utf-8")
        presentation = (ROOT / "ClawbarPresentation.js").read_text(encoding="utf-8")
        detail = (ROOT / "DetailCard.qml").read_text(encoding="utf-8")

        # The static registered-agent dot is a view-model fact, rendered generically.
        self.assertIn("dot: SIGNAL_PRESENTATIONS.registered_agent", presentation)
        self.assertIn('accessibleDescription: "Registered Agent"', presentation)
        self.assertIn(
            "Accessible.description: modelData.accessibleDescription",
            (ROOT / "RowSection.qml").read_text(encoding="utf-8"),
        )
        self.assertNotIn("modelData.activity", panel)
        self.assertNotIn('text: "Activity "', detail)

    def test_selected_rows_use_theme_aware_readable_secondary_colors(self) -> None:
        panel = (ROOT / "ClawbarPanel.qml").read_text(encoding="utf-8")
        color = (ROOT / "ClawbarColor.js").read_text(encoding="utf-8")
        section = (ROOT / "RowSection.qml").read_text(encoding="utf-8")

        self.assertIn(
            "ColorKit.readableColor(rawDim, foreground, panelSurface, 4.5)", panel
        )
        self.assertIn("readonly property color selectedDim", panel)
        # Selected-row secondaries resolve through the palette against each surface.
        self.assertIn("selectedSignalColor: function(tone)", color)
        self.assertIn("root.palette.selectedSignalColor(rowRoot.dot.tone)", section)
        self.assertIn("root.palette.selectedDim", section)
        self.assertIn("root.palette.dim", section)

    def test_healthy_row_labels_are_visually_quiet_but_accessible(self) -> None:
        presentation = (ROOT / "ClawbarPresentation.js").read_text(encoding="utf-8")
        section = (ROOT / "RowSection.qml").read_text(encoding="utf-8")

        # Label quietness is decided once per Operational Row view-model.
        self.assertIn("showNodeStatusLabel(item.state, historical)", presentation)
        self.assertIn("showAutomationStatusLabel(item, historical)", presentation)
        self.assertIn("Accessible.description", section)
        self.assertIn("Accessible.name: modelData.name", section)

    def test_selected_operational_rows_expand_details_inside_their_delegates(
        self,
    ) -> None:
        panel = (ROOT / "ClawbarPanel.qml").read_text(encoding="utf-8")
        section = (ROOT / "RowSection.qml").read_text(encoding="utf-8")

        # A single shared DetailCard component is loaded only for the open row.
        self.assertEqual(section.count("DetailCard {"), 1)
        self.assertIn("sourceComponent: detailCardComponent", section)
        self.assertNotIn("DetailCard {", panel)
        self.assertEqual(
            sorted(path.name for path in ROOT.glob("*DetailCard.qml")),
            ["DetailCard.qml"],
        )
        self.assertNotIn("id: selectedCard", panel)

    def test_operational_details_use_compact_single_line_timestamps(self) -> None:
        details = (ROOT / "DetailCard.qml").read_text(encoding="utf-8")

        self.assertIn("modelData.spoken", details)
        self.assertNotIn("wrapMode: Text.Wrap", details)
        self.assertIn("wrapMode: Text.NoWrap", details)
        self.assertIn("elide: Text.ElideRight", details)
        self.assertIn("Accessible.description", details)

    def test_panel_reads_only_the_operational_panel_model(self) -> None:
        panel = (ROOT / "ClawbarPanel.qml").read_text(encoding="utf-8")
        widget = (ROOT / "Clawbar.qml").read_text(encoding="utf-8")

        self.assertNotIn("root.snapshot.", panel)
        self.assertNotIn("root.metadata.", panel)
        self.assertNotIn("required property var snapshot", panel)
        self.assertNotIn('import "ClawbarSnapshot.js"', panel)
        self.assertIn("required property var panelModel", panel)
        self.assertIn("panelModel: root.operationalPanelModel", widget)

    def test_demo_publishes_all_twelve_sanitized_scenarios(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            empty_path = root / "bin"
            empty_path.mkdir()
            environment = os.environ.copy()
            environment.update(
                {
                    "CLAWBAR_DEMO_NO_RESCAN": "1",
                    "PATH": str(empty_path),
                    "XDG_RUNTIME_DIR": str(root / "runtime"),
                    "XDG_STATE_HOME": str(root / "state"),
                }
            )
            listed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "clawbar_demo.py"),
                    "--list-scenarios",
                ],
                cwd=ROOT,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(tuple(listed.stdout.splitlines()), DEMO_SCENARIOS)
            self.assertEqual(len(DEMO_SCENARIOS), 12)
            snapshots = {}
            for scenario in DEMO_SCENARIOS:
                with self.subTest(scenario=scenario):
                    completed = subprocess.run(
                        [
                            sys.executable,
                            str(ROOT / "scripts" / "clawbar_demo.py"),
                            scenario,
                            "--snapshot",
                            str(root / f"{scenario}.json"),
                        ],
                        cwd=ROOT,
                        env=environment,
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    snapshot = json.loads(completed.stdout)
                    self.assertEqual(snapshot["demoScenario"], scenario)
                    snapshots[scenario] = snapshot
                    serialized = json.dumps(snapshot)
                    for prohibited in (
                        "hostname",
                        "account",
                        "destination",
                        "token",
                        "message",
                        "rawError",
                        "/home/",
                    ):
                        self.assertNotIn(prohibited, serialized)
            healthy = dict(snapshots["healthy"])
            registered = dict(snapshots["registered-agents"])
            healthy.pop("demoScenario")
            registered.pop("demoScenario")
            self.assertNotEqual(healthy, registered)
            grouped = snapshots["grouped-incidents"]
            self.assertEqual(
                grouped["bar"],
                {"kind": "attention", "count": 2, "severity": "critical"},
            )
            self.assertEqual(
                [node["state"] for node in grouped["fleet"]["nodes"]],
                ["healthy", "offline", "offline"],
            )

    def test_demo_reproduces_grouped_incidents_and_recovery_without_private_content(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            bin_directory = root / "bin"
            bin_directory.mkdir()
            notification_log = root / "notifications.jsonl"
            notify_send = bin_directory / "notify-send"
            notify_send.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                "with open(os.environ['NOTIFICATION_LOG'], 'a', encoding='utf-8') as output:\n"
                "    output.write(json.dumps(sys.argv[1:]) + '\\n')\n",
                encoding="utf-8",
            )
            notify_send.chmod(0o755)
            environment = os.environ.copy()
            environment.update(
                {
                    "PATH": f"{bin_directory}:{environment['PATH']}",
                    "CLAWBAR_DEMO_NO_RESCAN": "1",
                    "XDG_RUNTIME_DIR": str(root / "runtime"),
                    "XDG_STATE_HOME": str(root / "state"),
                    "NOTIFICATION_LOG": str(notification_log),
                }
            )

            for scenario in ("healthy", "grouped-incidents", "recovery"):
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "scripts" / "clawbar_demo.py"),
                        scenario,
                    ],
                    cwd=ROOT,
                    env=environment,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                snapshot = json.loads(completed.stdout)
                self.assertEqual(snapshot["demoScenario"], scenario)

            self.assertTrue((root / "runtime" / "clawbar" / "demo-active").is_file())
            self.assertFalse((root / "runtime" / "clawbar" / "incidents.json").exists())
            demo_incidents = (
                root / "runtime" / "clawbar-demo" / "clawbar" / "incidents.json"
            )
            self.assertTrue(demo_incidents.is_file())
            subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "clawbar_collect.py")],
                cwd=ROOT,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            preserved = json.loads(
                (root / "state" / "clawbar" / "snapshot.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(preserved["demoScenario"], "recovery")

            subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "clawbar_demo.py"), "--resume"],
                cwd=ROOT,
                env=environment,
                check=True,
            )
            self.assertEqual(
                (root / "runtime" / "clawbar" / "demo-active").read_text(
                    encoding="utf-8"
                ),
                "0\n",
            )
            self.assertFalse(demo_incidents.exists())

            notifications = [
                json.loads(line)
                for line in notification_log.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(notifications), 2)
            self.assertTrue(
                notifications[0][2].endswith("/assets/clawbar-incident.svg")
            )
            self.assertEqual(notifications[0][3], "2 incidents detected")
            self.assertTrue(
                notifications[1][2].endswith("/assets/clawbar-recovered.svg")
            )
            self.assertEqual(notifications[1][3], "2 incidents resolved")

            serialized = (root / "state" / "clawbar" / "snapshot.json").read_text(
                encoding="utf-8"
            )
            for prohibited in (
                "hostname",
                "account",
                "destination",
                "token",
                "message",
                "rawError",
                "/home/",
            ):
                self.assertNotIn(prohibited, serialized)

    def test_submission_draft_matches_marketplace_issue_form(self) -> None:
        title = (ROOT / "MARKETPLACE_SUBMISSION_TITLE.txt").read_text(encoding="utf-8")
        body = (ROOT / "MARKETPLACE_SUBMISSION.md").read_text(encoding="utf-8")
        headings = [
            "### Repository URL",
            "### Category",
            "### Tags",
            "### Suggest a missing tag",
            "### Maintainer notes",
            "### Submission checklist",
        ]
        checklist = [
            "- [x] The repository is public and contains installation and removal instructions.",
            "- [x] I have documented the plugin license and any external dependencies.",
            "- [x] I confirm that I own or have permission to submit this plugin and its preview assets.",
            "- [x] The plugin does not overwrite user configuration without explicit consent.",
            "- [x] I understand that approval is for listing and is not a security review.",
        ]

        self.assertEqual(title, "[Plugin]: Clawbar\n")
        self.assertEqual(
            [line for line in body.splitlines() if line.startswith("### ")],
            headings,
        )
        self.assertIn("\nhttps://github.com/yasuhito/clawbar\n", body)
        self.assertIn("\nWidgets\n", body)
        self.assertIn("\nai, bar, quickshell\n", body)
        self.assertEqual(
            [line for line in body.splitlines() if line.startswith("- [x]")],
            checklist,
        )

    def test_repository_excludes_generated_and_systemd_artifacts(self) -> None:
        tracked = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout.split(b"\0")
        tracked_paths = {Path(path.decode("utf-8")) for path in tracked if path}

        for path in tracked_paths:
            with self.subTest(path=path):
                self.assertNotIn(".playwright-cli", path.parts)
                self.assertNotIn("__pycache__", path.parts)
                self.assertNotIn(path.suffix, {".pyc", ".pyo", ".pyd"})
                self.assertNotIn(path.suffix, {".service", ".timer"})


if __name__ == "__main__":
    unittest.main()
