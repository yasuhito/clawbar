import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "yasuhito.clawbar"

  property string state: "starting"
  property string resolutionSource: "unresolved"
  property bool refreshPending: false
  property string collectorPath: decodeURIComponent(String(Qt.resolvedUrl("scripts/clawbar_collect.py")).replace(/^file:\/\//, ""))
  property string snapshotPath: {
    var stateHome = Quickshell.env("XDG_STATE_HOME")
    var base = stateHome ? stateHome : Quickshell.env("HOME") + "/.local/state"
    return base + "/clawbar/snapshot.json"
  }
  property int refreshIntervalSeconds: {
    var configured = parseInt(Quickshell.env("CLAWBAR_REFRESH_INTERVAL_SECONDS"))
    return isNaN(configured) ? 30 : Math.max(15, Math.min(300, configured))
  }
  property string summary: {
    if (state === "healthy") {
      if (resolutionSource === "node_host") return "Node-host OpenClaw Gateway healthy"
      if (resolutionSource === "configured_remote") return "Remote OpenClaw Gateway healthy"
      return "Local OpenClaw Gateway healthy"
    }
    if (state === "unstable") return "OpenClaw Gateway unstable"
    if (state === "offline") return "OpenClaw Gateway offline"
    return "OpenClaw Gateway status unavailable"
  }

  function readSnapshot() {
    if (!cacheReader.running) cacheReader.running = true
  }

  function requestCollection() {
    if (collector.running) {
      refreshPending = true
    } else {
      collector.running = true
    }
  }

  function applySnapshot(snapshot) {
    if (snapshot.schemaVersion !== 1 || !snapshot.gateway)
      throw new Error("Unsupported Clawbar snapshot")
    var nextState = String(snapshot.gateway.state || "unknown")
    if (nextState !== "healthy" && nextState !== "unstable" && nextState !== "offline")
      nextState = "unknown"
    state = nextState
    resolutionSource = String(snapshot.resolutionSource || "unresolved")
  }

  Component.onCompleted: readSnapshot()

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  Process {
    id: cacheReader
    command: ["cat", root.snapshotPath]
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          root.applySnapshot(JSON.parse(text))
        } catch (_) {
          root.state = "unknown"
        }
      }
    }
    onExited: function(exitCode) {
      if (exitCode !== 0) root.state = "unknown"
    }
  }

  Process {
    id: collector
    command: [
      "python3",
      root.collectorPath,
      "--refresh-interval",
      String(root.refreshIntervalSeconds)
    ]
    onExited: function(_) {
      root.readSnapshot()
      if (root.refreshPending) {
        root.refreshPending = false
        collector.running = true
      }
    }
  }

  Timer {
    interval: root.refreshIntervalSeconds * 1000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.requestCollection()
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.state === "healthy" ? "󰚩" : "󰀦"
    active: root.state !== "healthy"
    slotSize: Style.bar.statusSlot
    fontSize: Style.font.caption
    tooltipText: root.summary
    onPressed: root.requestCollection()
  }
}
