import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "yasuhito.clawbar"

  property string state: "starting"
  property int automationFailures: 0
  property string summary: "Checking OpenClaw…"

  function refresh() {
    if (!collector.running) collector.running = true
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  Process {
    id: collector
    command: ["cat", Quickshell.env("HOME") + "/.local/state/clawbar/snapshot.json"]
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          var snapshot = JSON.parse(text)
          root.state = String(snapshot.state || "unknown")
          root.automationFailures = Number(snapshot.automationFailures || 0)
          root.summary = String(snapshot.summary || "OpenClaw status unavailable")
        } catch (_) {
          root.state = "unknown"
          root.summary = "OpenClaw status unavailable"
        }
      }
    }
    onExited: function(exitCode) {
      if (exitCode !== 0) {
        root.state = "unknown"
        root.summary = "OpenClaw status unavailable"
      }
    }
  }

  Timer {
    interval: 60000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.refresh()
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.state === "healthy" && root.automationFailures === 0 ? "󰚩" : "󰀦"
    active: root.state !== "healthy" || root.automationFailures > 0
    slotSize: Style.bar.statusSlot
    fontSize: Style.font.caption
    tooltipText: root.summary
    onPressed: if (root.bar) root.bar.run("openclaw gateway status --deep")
  }
}
