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
  property int selectedIndex: -1
  property var expandedNodes: ({})
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
  readonly property var rows: Logic.panelRows(lastSnapshot)
  readonly property var nodes: Logic.fleetNodes(lastSnapshot)
  readonly property var agents: Logic.agents(lastSnapshot)
  readonly property int workingCount: Logic.workingCount(lastSnapshot)
  readonly property var selectedRow: selectedIndex >= 0 && selectedIndex < rows.length
    ? rows[selectedIndex] : null
  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color dim: Color.muted
  readonly property color accent: Color.accent
  readonly property color urgent: bar ? bar.urgent : Color.urgent
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family

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
    if (rows.length === 0) selectedIndex = -1
    else if (selectedIndex < 0 || selectedIndex >= rows.length) selectedIndex = 0
  }

  function refreshFreshness() {
    nowMs = Date.now()
    if (lastSnapshot) state = Logic.snapshotState(lastSnapshot, nowMs)
  }

  function open() {
    opened = true
    if (rows.length > 0 && selectedIndex < 0) selectedIndex = 0
  }

  function toggle() {
    if (opened) close()
    else open()
  }

  function close() {
    opened = false
  }

  function moveSelection(delta) {
    selectedIndex = Logic.moveFocus(selectedIndex, rows.length, delta)
    Qt.callLater(root.ensureSelectionVisible)
  }

  function ensureSelectionVisible() {
    if (selectedIndex < 0) return
    var delegate = selectedIndex < nodes.length
      ? nodeRepeater.itemAt(selectedIndex)
      : agentRepeater.itemAt(selectedIndex - nodes.length)
    if (!delegate) return
    var top = delegate.mapToItem(contentColumn, 0, 0).y
    var bottom = top + delegate.height
    if (top < panelFlick.contentY) panelFlick.contentY = top
    else if (bottom > panelFlick.contentY + panelFlick.height)
      panelFlick.contentY = Math.max(0, bottom - panelFlick.height)
  }

  function activateSelection() {
    if (!selectedRow || selectedRow.kind !== "node") return
    var next = Object.assign({}, expandedNodes)
    next[selectedRow.index] = !next[selectedRow.index]
    expandedNodes = next
    Qt.callLater(root.ensureSelectionVisible)
  }

  function stateColor(value) {
    if (value === "offline" || value === "configuration_error") return urgent
    if (value === "healthy") return accent
    return dim
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
    text: "󰚩" + (root.state === "healthy" && root.workingCount > 0 ? " " + root.workingCount : "")
    active: root.state !== "healthy"
    slotSize: Style.bar.statusSlot
    fontSize: Style.font.caption
    tooltipText: root.summary
    onPressed: function(buttonCode) {
      if (buttonCode === Qt.MiddleButton) root.requestCollection()
      else root.toggle()
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(360))
    contentHeight: panel.fittedContentHeight(contentColumn.implicitHeight, Style.space(560))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent

      onMoveRequested: function(dx, dy) {
        if (dy !== 0) root.moveSelection(dy)
        else if (dx !== 0) root.moveSelection(dx)
      }
      onActivateRequested: root.activateSelection()
      onCloseRequested: root.close()
      onTextKey: function(text) {
        if (text === "j" || text === "J") root.moveSelection(1)
        else if (text === "k" || text === "K") root.moveSelection(-1)
        else if (text === "r" || text === "R") root.requestCollection()
      }

      Flickable {
        id: panelFlick
        anchors.fill: parent
        contentWidth: width
        contentHeight: contentColumn.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        interactive: contentHeight > height

        Column {
          id: contentColumn
          width: panelFlick.width
          spacing: Style.space(4)

          Item {
            width: parent.width
            height: Style.space(48)

            Text {
              anchors.left: parent.left
              anchors.top: parent.top
              text: "Clawbar"
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.title
              font.bold: true
            }

            Text {
              anchors.left: parent.left
              anchors.bottom: parent.bottom
              text: root.summary
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }

            Text {
              anchors.right: parent.right
              anchors.bottom: parent.bottom
              text: root.lastSnapshot ? Logic.relativeTime(root.lastSnapshot.generatedAt, root.nowMs) : ""
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }
          }

          Text {
            width: parent.width
            text: "FLEET"
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            font.bold: true
          }

          Text {
            visible: root.lastSnapshot && root.lastSnapshot.fleet && !root.lastSnapshot.fleet.available
            width: parent.width
            text: "Node metadata unavailable"
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.body
          }

          Text {
            visible: root.lastSnapshot && root.lastSnapshot.fleet
              && root.lastSnapshot.fleet.available && root.nodes.length === 0
            width: parent.width
            text: "Empty Fleet"
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.body
          }

          Repeater {
            id: nodeRepeater
            model: root.nodes

            delegate: Rectangle {
              id: nodeRow
              required property var modelData
              required property int index
              readonly property bool selected: root.selectedIndex === index
              readonly property bool expanded: !!root.expandedNodes[index]
              width: contentColumn.width
              height: Style.space(expanded ? 72 : 48)
              radius: Style.cornerRadius
              color: selected ? Style.selectedFillFor(root.foreground, root.accent) : "transparent"
              border.width: selected ? 1 : 0
              border.color: root.accent

              MouseArea {
                anchors.fill: parent
                onClicked: {
                  root.selectedIndex = nodeRow.index
                  root.activateSelection()
                }
              }

              Text {
                anchors.left: parent.left
                anchors.leftMargin: Style.space(8)
                anchors.verticalCenter: nodeTitle.verticalCenter
                text: nodeRow.expanded ? "▾" : "›"
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
              }

              Rectangle {
                anchors.left: parent.left
                anchors.leftMargin: Style.space(24)
                anchors.verticalCenter: nodeTitle.verticalCenter
                width: Style.space(6)
                height: width
                radius: width / 2
                color: root.stateColor(nodeRow.modelData.state)
              }

              Text {
                id: nodeTitle
                anchors.left: parent.left
                anchors.leftMargin: Style.space(38)
                anchors.right: nodeState.left
                anchors.rightMargin: Style.space(8)
                anchors.top: parent.top
                anchors.topMargin: Style.space(9)
                text: nodeRow.modelData.name
                elide: Text.ElideRight
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                font.bold: true
              }

              Text {
                id: nodeState
                anchors.right: parent.right
                anchors.rightMargin: Style.space(8)
                anchors.verticalCenter: nodeTitle.verticalCenter
                text: nodeRow.modelData.state === "healthy" ? "Healthy" : "Offline"
                color: nodeRow.modelData.state === "offline" ? root.urgent : root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }

              Text {
                visible: nodeRow.expanded
                anchors.left: nodeTitle.left
                anchors.right: parent.right
                anchors.rightMargin: Style.space(8)
                anchors.bottom: parent.bottom
                anchors.bottomMargin: Style.space(8)
                text: {
                  var parts = [nodeRow.modelData.platform, nodeRow.modelData.model, nodeRow.modelData.version]
                    .filter(function(value) { return !!value })
                  var age = Logic.relativeTime(nodeRow.modelData.lastSeenAt, root.nowMs)
                  if (age) parts.push("Seen " + age)
                  return parts.length > 0 ? parts.join(" · ") : "No additional Operational Metadata"
                }
                elide: Text.ElideRight
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
            }
          }

          Text {
            width: parent.width
            topPadding: Style.space(8)
            text: "AGENTS"
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            font.bold: true
          }

          Text {
            visible: root.lastSnapshot && root.lastSnapshot.agents && !root.lastSnapshot.agents.available
            width: parent.width
            text: "Agent and Task metadata unavailable"
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.body
          }

          Repeater {
            id: agentRepeater
            model: root.agents

            delegate: Rectangle {
              id: agentRow
              required property var modelData
              required property int index
              readonly property int rowIndex: root.nodes.length + index
              readonly property bool selected: root.selectedIndex === rowIndex
              readonly property string activityText: Logic.activityLabel(modelData.activity)
              width: contentColumn.width
              height: Style.space(48)
              radius: Style.cornerRadius
              color: selected ? Style.selectedFillFor(root.foreground, root.accent) : "transparent"
              border.width: selected ? 1 : 0
              border.color: root.accent

              MouseArea {
                anchors.fill: parent
                onClicked: root.selectedIndex = agentRow.rowIndex
              }

              Rectangle {
                visible: agentRow.modelData.activity === "working" || agentRow.modelData.activity === "waiting"
                anchors.left: parent.left
                anchors.leftMargin: Style.space(10)
                anchors.verticalCenter: agentName.verticalCenter
                width: Style.space(6)
                height: width
                radius: width / 2
                color: agentRow.modelData.activity === "working" ? root.accent : root.dim
              }

              Text {
                id: agentName
                anchors.left: parent.left
                anchors.leftMargin: Style.space(26)
                anchors.right: agentActivity.left
                anchors.rightMargin: Style.space(8)
                anchors.top: parent.top
                anchors.topMargin: Style.space(6)
                text: agentRow.modelData.name
                elide: Text.ElideRight
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                font.bold: true
              }

              Text {
                id: agentActivity
                anchors.right: parent.right
                anchors.rightMargin: Style.space(8)
                anchors.verticalCenter: agentName.verticalCenter
                text: agentRow.activityText
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }

              Text {
                anchors.left: agentName.left
                anchors.right: parent.right
                anchors.rightMargin: Style.space(8)
                anchors.bottom: parent.bottom
                anchors.bottomMargin: Style.space(6)
                text: Logic.taskResultLabel(agentRow.modelData.taskResult, root.nowMs)
                elide: Text.ElideRight
                color: agentRow.modelData.taskResult
                  && agentRow.modelData.taskResult.state === "failed" ? root.urgent : root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
            }
          }

          Rectangle {
            visible: root.selectedRow !== null
            width: parent.width
            height: selectedDetail.implicitHeight + Style.space(16)
            radius: Style.cornerRadius
            color: Style.selectedFillFor(root.foreground, Color.popups.background)

            Text {
              id: selectedDetail
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              anchors.margins: Style.space(8)
              text: {
                if (!root.selectedRow) return ""
                var title = root.selectedRow.kind === "node" ? "Node" : "Agent"
                var absolute = Logic.absoluteLocalTime(Logic.rowTimestamp(root.selectedRow))
                return title + " · " + root.selectedRow.item.name
                  + (absolute ? "\nObserved " + absolute : "\nNo completion timestamp")
              }
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              wrapMode: Text.Wrap
            }
          }
        }
      }
    }
  }
}
