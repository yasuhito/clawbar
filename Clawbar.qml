import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "ClawbarSnapshot.js" as Snapshot
import "ClawbarPresentation.js" as Presentation
import "ClawbarPanelModel.js" as PanelModel
import "ClawbarColor.js" as ColorKit

BarWidget {
  id: root
  moduleName: "io.github.yasuhito.clawbar"

  property string state: "starting"
  property string resolutionSource: "unresolved"
  property var lastSnapshot: null
  property bool cacheReadPending: false
  property bool themeReadPending: false
  property string themeReadOutput: ""
  property bool collectionAttempted: false
  property bool opened: false
  property string refreshFeedback: "idle"
  property double nowMs: Date.now()
  readonly property color signalForeground: bar ? bar.foreground : Color.foreground
  property color healthyColor: signalForeground
  property color warningColor: Color.accent
  readonly property var themeGeneration: Color.shellValues
  readonly property string themeColorsPath: Color.currentThemePath + "/colors.toml"
  property string collectorPath: decodeURIComponent(
    String(Qt.resolvedUrl("scripts/clawbar_collect.py")).replace(/^file:\/\//, "")
  )
  readonly property var collectorService: {
    if (!bar || !bar.shell || typeof bar.shell.serviceFor !== "function") return null
    return bar.shell.serviceFor(root.moduleName)
  }
  readonly property string barSeverity: Snapshot.barSeverity(lastSnapshot, state)
  readonly property int barCount: Snapshot.barCount(lastSnapshot, state)
  readonly property bool developerDemo: !!lastSnapshot && typeof lastSnapshot.demoScenario === "string"
  readonly property string baseSummary: Presentation.summary(state, resolutionSource, barCount, barSeverity)
  readonly property string refreshSummary: Presentation.refreshSummary(
    baseSummary, refreshFeedback, lastSnapshot !== null
  )
  readonly property string summary: developerDemo
    ? "Developer demo · " + refreshSummary : refreshSummary
  readonly property string basePanelSummary: Presentation.panelSummary(
    state, resolutionSource, barCount, barSeverity, Presentation.panelSignal(lastSnapshot, state).label
  )
  readonly property string refreshPanelSummary: Presentation.refreshSummary(
    basePanelSummary, refreshFeedback, lastSnapshot !== null
  )
  readonly property string panelSummary: developerDemo
    ? "Developer demo · " + refreshPanelSummary : refreshPanelSummary
  readonly property var operationalSectionData: Snapshot.sectionData(lastSnapshot, state)
  readonly property var operationalPanelModel: PanelModel.create(
    operationalSectionData, Presentation.panelSections(operationalSectionData)
  )
  readonly property var gatewaySignal: Presentation.panelSignal(lastSnapshot, state)
  readonly property var barSignal: Presentation.signalPresentation(
    barSeverity === "critical" ? "failed" : barSeverity === "warning" ? "waiting" : "healthy"
  )
  readonly property color barSignalColor: ColorKit.signalColor(
    barSignal.tone,
    signalForeground,
    Color.accent,
    bar ? bar.urgent : Color.urgent,
    Color.muted,
    null,
    warningColor
  )

  function loadThemeColors(raw) {
    healthyColor = ColorKit.themeColorFromTheme(raw, "green", signalForeground)
    warningColor = ColorKit.themeColorFromTheme(raw, "yellow", Color.accent)
  }

  function readThemeColors() {
    if (themeReader.running) {
      themeReadPending = true
      return
    }
    themeReadOutput = ""
    themeReader.running = true
  }

  function consumeThemeRead(exitCode) {
    if (themeReadPending) {
      themeReadPending = false
      themeReadOutput = ""
      themeReader.running = true
      return
    }
    loadThemeColors(exitCode === 0 ? themeReadOutput : "")
  }

  onThemeGenerationChanged: readThemeColors()

  function readSnapshot() {
    var action = Snapshot.requestRefresh(cacheReader.running)
    cacheReadPending = action.pending
    if (action.start) cacheReader.running = true
  }

  function consumeCacheRead(exitCode) {
    var action = Snapshot.consumeRefresh(cacheReader.running, cacheReadPending)
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
    refreshFeedbackTimer.stop()
    if (!collectorService) {
      console.warn("Clawbar scheduler service unavailable")
      if (lastSnapshot === null) {
        state = "no_data"
      } else {
        refreshFeedback = "failed"
        refreshFeedbackTimer.restart()
      }
      return
    }
    refreshFeedback = "refreshing"
    if (lastSnapshot === null) state = "collecting"
    collectorService.requestCollection(true)
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
    state = Snapshot.snapshotState(snapshot, Date.now())
    resolutionSource = String(snapshot.resolutionSource || "unresolved")
    lastSnapshot = snapshot
  }

  function refreshFreshness() {
    nowMs = Date.now()
    if (lastSnapshot) state = Snapshot.snapshotState(lastSnapshot, nowMs)
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

  Component.onCompleted: {
    readSnapshot()
    readThemeColors()
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  Process {
    id: cacheReader
    command: ["python3", root.collectorPath, "--read-cache"]
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
    id: themeReader
    command: ["python3", root.collectorPath, "--read-theme-colors", root.themeColorsPath]
    stdout: StdioCollector {
      onStreamFinished: root.themeReadOutput = text
    }
    onExited: function(exitCode) {
      Qt.callLater(function() { root.consumeThemeRead(exitCode) })
    }
  }
  Timer {
    interval: 1000
    running: root.lastSnapshot !== null
    repeat: true
    onTriggered: root.refreshFreshness()
  }
  Timer {
    id: refreshFeedbackTimer
    interval: 6000
    repeat: false
    onTriggered: root.refreshFeedback = "idle"
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
          width: Style.bar.iconCanvas
          height: width
          color: root.barSignalColor
          animated: button.tooltipHovered
            || (!!root.collectorService && root.collectorService.collecting)
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
    function onCollectionFinished(interactive, succeeded) {
      if (interactive) {
        root.refreshFeedback = succeeded ? "idle" : "failed"
        if (!succeeded) root.refreshFeedbackTimer.restart()
      }
      root.consumeCollection()
    }
  }

  ClawbarPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    panelModel: root.operationalPanelModel
    gatewaySignal: root.gatewaySignal
    nowMs: root.nowMs
    summary: root.panelSummary
    verifyingCandidate: root.collectorService ? root.collectorService.verifyingCandidate : false
    healthy: root.healthyColor
    warning: root.warningColor
    onRefreshRequested: root.requestCollection()
    onCandidateVerificationRequested: function(candidateKey) {
      root.verifyCandidate(candidateKey)
    }
  }
}
