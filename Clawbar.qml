pragma ComponentBehavior: Bound

import QtQuick
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

  property string gatewayState: "starting"
  property string resolutionSource: "unresolved"
  property var lastSnapshot: null
  property bool cacheReadPending: false
  property bool themeReadPending: false
  property string themeReadOutput: ""
  property bool collectionAttempted: false
  property bool opened: false
  property string refreshFeedback: "idle"
  property double nowMs: Date.now()
  readonly property color signalForeground: dynamicMember(bar, "foreground", Color.foreground)
  property color healthyColor: signalForeground
  property color warningColor: Color.accent
  readonly property var themeGeneration: Color.shellValues
  readonly property string themeColorsPath: Color.currentThemePath + "/colors.toml"
  property string collectorPath: decodeURIComponent(String(Qt.resolvedUrl("scripts/clawbar_collect.py")).replace(/^file:\/\//, ""))
  readonly property var collectorService: {
    var shell = dynamicMember(bar, "shell", null);
    if (!shell || typeof shell.serviceFor !== "function")
      return null;
    return shell.serviceFor(root.moduleName);
  }
  readonly property string barSeverity: Snapshot.barSeverity(lastSnapshot, gatewayState)
  readonly property int barCount: Snapshot.barCount(lastSnapshot, gatewayState)
  readonly property bool developerDemo: !!lastSnapshot && typeof lastSnapshot.demoScenario === "string"
  readonly property string baseSummary: Presentation.summary(gatewayState, resolutionSource, barCount, barSeverity)
  readonly property string refreshSummary: Presentation.refreshSummary(baseSummary, refreshFeedback, lastSnapshot !== null)
  readonly property string summary: developerDemo ? "Developer demo · " + refreshSummary : refreshSummary
  readonly property string basePanelSummary: Presentation.panelSummary(gatewayState, resolutionSource, barCount, barSeverity, Presentation.panelSignal(lastSnapshot, gatewayState).label)
  readonly property string refreshPanelSummary: Presentation.refreshSummary(basePanelSummary, refreshFeedback, lastSnapshot !== null)
  readonly property string panelSummary: developerDemo ? "Developer demo · " + refreshPanelSummary : refreshPanelSummary
  readonly property var operationalSectionData: Snapshot.sectionData(lastSnapshot, gatewayState)
  readonly property var operationalPanelModel: PanelModel.create(operationalSectionData, Presentation.panelSections(operationalSectionData))
  readonly property var gatewaySignal: Presentation.panelSignal(lastSnapshot, gatewayState)
  readonly property var barSignal: Presentation.signalPresentation(barSeverity === "critical" ? "failed" : barSeverity === "warning" ? "waiting" : "healthy")
  readonly property color barSignalColor: ColorKit.signalColor(barSignal.tone, signalForeground, Color.accent, dynamicMember(bar, "urgent", Color.urgent), Color.muted, null, warningColor)
  readonly property int barStatusSlot: Style.barToken("status-slot", 21)
  readonly property int barIconCanvas: Style.barToken("icon-canvas", 16)

  function dynamicMember(object, name, fallback) {
    return object && name in object ? object[name] : fallback;
  }

  function loadThemeColors(raw) {
    healthyColor = ColorKit.themeColorFromTheme(raw, "green", signalForeground);
    warningColor = ColorKit.themeColorFromTheme(raw, "yellow", Color.accent);
  }

  function readThemeColors() {
    if (themeReader.running) {
      themeReadPending = true;
      return;
    }
    themeReadOutput = "";
    themeReader.running = true;
  }

  function consumeThemeRead() {
    if (themeReadPending) {
      themeReadPending = false;
      themeReadOutput = "";
      themeReader.running = true;
      return;
    }
    loadThemeColors(themeReadOutput);
  }

  onThemeGenerationChanged: readThemeColors()

  function readSnapshot() {
    var action = Snapshot.requestRefresh(cacheReader.running);
    cacheReadPending = action.pending;
    if (action.start)
      cacheReader.running = true;
  }

  function consumeCacheRead(exitCode) {
    var action = Snapshot.consumeRefresh(cacheReader.running, cacheReadPending);
    cacheReadPending = action.pending;
    if (action.wait) {
      Qt.callLater(function () {
        root.consumeCacheRead(exitCode);
      });
      return;
    }
    if (exitCode !== 0 && lastSnapshot === null)
      gatewayState = collectionAttempted ? "no_data" : "collecting";
    if (action.start)
      cacheReader.running = true;
  }

  function requestCollection() {
    refreshFeedbackTimer.stop();
    if (!collectorService) {
      console.warn("Clawbar scheduler service unavailable");
      if (lastSnapshot === null) {
        gatewayState = "no_data";
      } else {
        refreshFeedback = "failed";
        refreshFeedbackTimer.restart();
      }
      return;
    }
    refreshFeedback = "refreshing";
    if (lastSnapshot === null)
      gatewayState = "collecting";
    collectorService.requestCollection(true);
  }

  function consumeCollection() {
    collectionAttempted = true;
    readSnapshot();
  }
  function verifyCandidate(candidateKey) {
    if (!collectorService || !candidateKey)
      return;
    collectorService.verifyCandidate(candidateKey);
  }

  function applySnapshot(snapshot) {
    gatewayState = Snapshot.snapshotState(snapshot, Date.now());
    resolutionSource = String(snapshot.resolutionSource || "unresolved");
    lastSnapshot = snapshot;
  }

  function refreshFreshness() {
    nowMs = Date.now();
    if (lastSnapshot)
      gatewayState = Snapshot.snapshotState(lastSnapshot, nowMs);
  }

  function open() {
    opened = true;
  }

  function toggle() {
    if (opened)
      close();
    else
      open();
  }

  function close() {
    opened = false;
  }

  Component.onCompleted: {
    readSnapshot();
    readThemeColors();
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  Process {
    id: cacheReader
    command: ["python3", root.collectorPath, "--read-cache"]
    stdout: StdioCollector {
      onStreamFinished: {
        var snapshot;
        try {
          snapshot = JSON.parse(text);
        } catch (_) {
          if (root.lastSnapshot === null)
            root.gatewayState = root.collectionAttempted ? "no_data" : "collecting";
          return;
        }
        try {
          root.applySnapshot(snapshot);
        } catch (error) {
          console.warn("Clawbar rejected Snapshot: " + error.message);
          if (root.lastSnapshot === null)
            root.gatewayState = root.collectionAttempted ? "no_data" : "collecting";
        }
      }
    }
    onRunningChanged: {
      if (!running)
        Qt.callLater(root.consumeCacheRead);
    }
  }
  Process {
    id: themeReader
    command: ["python3", root.collectorPath, "--read-theme-colors", root.themeColorsPath]
    stdout: StdioCollector {
      onStreamFinished: root.themeReadOutput = text
    }
    onRunningChanged: {
      if (!running)
        Qt.callLater(root.consumeThemeRead);
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
    slotSize: root.barStatusSlot
    opticalSize: root.barIconCanvas
    tooltipText: root.summary
    iconComponent: Component {
      Item {
        ClawMark {
          anchors.centerIn: parent
          width: root.barIconCanvas
          height: width
          color: root.barSignalColor
          animated: button.tooltipHovered || (!!root.collectorService && root.collectorService.collecting)
        }
      }
    }
    onPressed: function (buttonCode) {
      if (buttonCode === Qt.MiddleButton)
        root.requestCollection();
      else
        root.toggle();
    }
  }

  Connections {
    target: root.collectorService
    function onCollectionFinished(interactive, succeeded) {
      if (interactive) {
        root.refreshFeedback = succeeded ? "idle" : "failed";
        if (!succeeded)
          refreshFeedbackTimer.restart();
      }
      root.consumeCollection();
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
    onCandidateVerificationRequested: function (candidateKey) {
      root.verifyCandidate(candidateKey);
    }
  }
}
