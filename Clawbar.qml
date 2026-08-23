import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "ClawbarLogic.js" as Logic

BarWidget {
  id: root
  moduleName: "io.github.yasuhito.clawbar"

  property string state: "starting"
  property string resolutionSource: "unresolved"
  property var lastSnapshot: null
  property bool cacheReadPending: false
  property bool collectionAttempted: false
  property bool opened: false
  property double nowMs: Date.now()
  readonly property color signalForeground: bar ? bar.foreground : Color.foreground
  property color healthyColor: signalForeground
  property color warningColor: Color.accent
  readonly property var themeGeneration: Color.shellValues
  property string collectorPath: decodeURIComponent(String(Qt.resolvedUrl("scripts/clawbar_collect.py")).replace(/^file:\/\//, ""))
  property string snapshotPath: {
    var stateHome = Quickshell.env("XDG_STATE_HOME")
    var base = stateHome ? stateHome : Quickshell.env("HOME") + "/.local/state"
    return base + "/clawbar/snapshot.json"
  }
  readonly property var collectorService: {
    if (!bar || !bar.shell || typeof bar.shell.serviceFor !== "function") return null
    return bar.shell.serviceFor(root.moduleName)
  }
  readonly property string barSeverity: Logic.barSeverity(lastSnapshot, state)
  readonly property int barCount: Logic.barCount(lastSnapshot, state)
  readonly property bool developerDemo: !!lastSnapshot && typeof lastSnapshot.demoScenario === "string"
  readonly property string baseSummary: Logic.summary(state, resolutionSource, barCount, barSeverity)
  readonly property string summary: developerDemo ? "Developer demo · " + baseSummary : baseSummary
  readonly property var barSignal: Logic.signalPresentation(
    barSeverity === "critical" ? "failed" : barSeverity === "warning" ? "waiting" : "healthy"
  )
  readonly property color barSignalColor: Logic.signalColor(
    barSignal.tone,
    signalForeground,
    Color.accent,
    bar ? bar.urgent : Color.urgent,
    Color.muted,
    null,
    warningColor
  )

  function loadThemeColors(raw) {
    healthyColor = Logic.themeColorFromTheme(raw, "green", signalForeground)
    warningColor = Logic.themeColorFromTheme(raw, "yellow", Color.accent)
  }

  property FileView themeColors: FileView {
    path: Color.currentThemePath + "/colors.toml"
    watchChanges: false
    printErrors: false
    onLoaded: root.loadThemeColors(text())
    onLoadFailed: root.loadThemeColors("")
  }

  onThemeGenerationChanged: if (themeColors) themeColors.reload()

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
    if (exitCode !== 0 && lastSnapshot === null)
      state = collectionAttempted ? "no_data" : "collecting"
    if (action.start) cacheReader.running = true
  }

  function requestCollection() {
    if (!collectorService) {
      console.warn("Clawbar scheduler service unavailable")
      if (lastSnapshot === null) state = "no_data"
      return
    }
    if (lastSnapshot === null) state = "collecting"
    collectorService.requestCollection()
  }

  function consumeCollection() {
    collectionAttempted = true
    readSnapshot()
  }
  function verifyCandidate(candidateKey) {
    if (!collectorService || !candidateKey) return
    collectorService.verifyCandidate(candidateKey)
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

  function openAutomationHistory(automationId) {
    if (!automationId || historyLauncher.running) return
    historyLauncher.command = [
      "xdg-terminal-exec",
      "python3",
      root.collectorPath,
      "--automation-history",
      automationId
    ]
    historyLauncher.running = true
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
          if (root.lastSnapshot === null)
            root.state = root.collectionAttempted ? "no_data" : "collecting"
        }
      }
    }
    onExited: function(exitCode) {
      Qt.callLater(function() { root.consumeCacheRead(exitCode) })
    }
  }
  Process {
    id: historyLauncher
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
    text: ""
    active: false
    slotSize: Style.bar.statusSlot
    opticalSize: Style.bar.iconCanvas
    tooltipText: root.summary
    iconComponent: Component {
      Item {
        ClawMark {
          anchors.centerIn: parent
          // Qt Shape keeps more path whitespace than the prototype SVG; 7/8
          // of the theme's optical canvas matches its 10px painted footprint.
          width: Style.bar.iconCanvas * 0.875
          height: width
          color: root.barSignalColor
        }
      }
    }
    onPressed: function(buttonCode) {
      if (buttonCode === Qt.MiddleButton) root.requestCollection()
      else root.toggle()
    }
  }

  Connections {
    target: root.collectorService
    function onCollectionFinished() {
      root.consumeCollection()
    }
  }

  ClawbarPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    snapshot: root.lastSnapshot
    state: root.state
    nowMs: root.nowMs
    summary: root.summary
    verifyingCandidate: root.collectorService ? root.collectorService.verifyingCandidate : false
    automationHistoryBusy: historyLauncher.running
    healthy: root.healthyColor
    warning: root.warningColor
    onRefreshRequested: root.requestCollection()
    onAutomationHistoryRequested: function(automationId) {
      root.openAutomationHistory(automationId)
    }
    onCandidateVerificationRequested: function(candidateKey) {
      root.verifyCandidate(candidateKey)
    }
  }
}
