import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "ClawbarLogic.js" as Logic

BarWidget {
  id: root
  moduleName: "yasuhito.clawbar"

  property string state: "starting"
  property string resolutionSource: "unresolved"
  property var lastSnapshot: null
  property bool refreshPending: false
  property bool cacheReadPending: false
  property bool opened: false
  property double nowMs: Date.now()
  property string collectorPath: decodeURIComponent(String(Qt.resolvedUrl("scripts/clawbar_collect.py")).replace(/^file:\/\//, ""))
  property string snapshotPath: {
    var stateHome = Quickshell.env("XDG_STATE_HOME")
    var base = stateHome ? stateHome : Quickshell.env("HOME") + "/.local/state"
    return base + "/clawbar/snapshot.json"
  }
  property int refreshIntervalSeconds: Logic.normalizeRefreshInterval(
    Quickshell.env("CLAWBAR_REFRESH_INTERVAL_SECONDS")
  )
  readonly property string summary: Logic.summary(state, resolutionSource)
  readonly property int workingCount: Logic.workingCount(lastSnapshot)

  function readSnapshot() {
    var action = Logic.requestRefresh(cacheReader.running)
    cacheReadPending = action.pending
    if (action.start) cacheReader.running = true
  }

  function consumeCacheRead(exitCode) {
    var action = Logic.consumeRefresh(cacheReader.running, cacheReadPending)
    cacheReadPending = action.pending
    if (action.wait) {
      Qt.callLater(function() { root.consumeCacheRead(exitCode) })
      return
    }
    if (exitCode !== 0) {
      lastSnapshot = null
      state = "unknown"
    }
    if (action.start) cacheReader.running = true
  }

  function requestCollection() {
    var action = Logic.requestRefresh(collector.running)
    refreshPending = action.pending
    if (action.start) collector.running = true
  }

  function consumeCollection() {
    var action = Logic.consumeRefresh(collector.running, refreshPending)
    refreshPending = action.pending
    if (action.wait) {
      Qt.callLater(function() { root.consumeCollection() })
      return
    }
    root.readSnapshot()
    if (action.start) collector.running = true
  }

  function applySnapshot(snapshot) {
    state = Logic.snapshotState(snapshot, Date.now())
    resolutionSource = String(snapshot.resolutionSource || "unresolved")
    lastSnapshot = snapshot
  }

  function refreshFreshness() {
    nowMs = Date.now()
    if (lastSnapshot) state = Logic.snapshotState(lastSnapshot, nowMs)
  }

  function open() {
    opened = true
  }

  function toggle() {
    if (opened) close()
    else open()
  }

  function close() {
    opened = false
  }

  function barMark() {
    if (state === "healthy" || state === "degraded") return "󰚩"
    if (state === "configuration_error") return "󰒓"
    if (state === "stale") return "󰔟"
    return "󰀦"
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
          root.lastSnapshot = null
          root.state = "unknown"
        }
      }
    }
    onExited: function(exitCode) {
      Qt.callLater(function() { root.consumeCacheRead(exitCode) })
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
      Qt.callLater(function() { root.consumeCollection() })
    }
  }

  Timer {
    interval: root.refreshIntervalSeconds * 1000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.requestCollection()
  }

  Timer {
    interval: 1000
    running: root.lastSnapshot !== null
    repeat: true
    onTriggered: root.refreshFreshness()
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.barMark()
      + (root.state === "healthy" && root.workingCount > 0 ? " " + root.workingCount : "")
    active: root.state !== "healthy"
    slotSize: Style.bar.statusSlot
    fontSize: Style.font.caption
    tooltipText: root.summary
    onPressed: function(buttonCode) {
      if (buttonCode === Qt.MiddleButton) root.requestCollection()
      else root.toggle()
    }
  }

  ClawbarPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    snapshot: root.lastSnapshot
    nowMs: root.nowMs
    summary: root.summary
    onRefreshRequested: root.requestCollection()
  }
}
