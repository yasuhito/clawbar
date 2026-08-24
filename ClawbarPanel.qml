import QtQuick
import qs.Commons
import qs.Ui
import "ClawbarLogic.js" as Logic

KeyboardPanel {
  id: root

  required property var snapshot
  required property string state
  property double nowMs: Date.now()
  property string summary: ""
  property string selectedKey: ""
  property int selectedIndexHint: 0
  property bool verifyingCandidate: false

  signal refreshRequested()
  signal candidateVerificationRequested(string candidateKey)

  readonly property var metadata: Logic.metadataSnapshot(snapshot, state)
  readonly property bool historical: Logic.historicalState(state)
  readonly property string observedAt: Logic.observationTime(snapshot, state)
  readonly property var rows: Logic.panelRows(snapshot, state)
  readonly property var nodes: Logic.fleetNodes(snapshot, state)
  readonly property var agents: Logic.agents(snapshot, state)
  readonly property var automations: Logic.automations(snapshot, state)
  readonly property var candidates: Logic.setupCandidates(snapshot, state)
  readonly property bool setupVisible: candidates.length > 0 || state === "setup_required"
    || (state === "configuration_error" && snapshot && snapshot.setup)
  readonly property bool configurationErrorVisible: state === "configuration_error"
  readonly property int selectedIndex: Logic.indexForKey(rows, selectedKey)
  readonly property var selectedRow: selectedIndex >= 0 ? rows[selectedIndex] : null
  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color dim: Color.muted
  readonly property color accent: Color.accent
  readonly property color urgent: bar ? bar.urgent : Color.urgent
  required property color healthy
  required property color warning
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property var gatewaySignal: Logic.panelSignal(snapshot, state)

  focusTarget: keyCatcher
  contentWidth: fittedContentWidth(Style.space(360))
  contentHeight: fittedContentHeight(contentColumn.implicitHeight, Style.space(560))

  function reconcileRows() {
    var selection = Logic.reconcileSelection(rows, selectedKey, selectedIndexHint)
    selectedKey = selection.key
    selectedIndexHint = selection.index < 0 ? 0 : selection.index
  }

  function selectRow(row) {
    if (!row) return
    selectedKey = row.key
    selectedIndexHint = Logic.indexForKey(rows, row.key)
    Qt.callLater(root.ensureSelectionVisible)
  }

  function moveSelection(delta) {
    var next = Logic.moveFocus(selectedIndex, rows.length, delta)
    if (next < 0) return
    selectedKey = rows[next].key
    selectedIndexHint = next
    Qt.callLater(root.ensureSelectionVisible)
  }

  function rowDelegate(row) {
    if (!row) return null
    if (row.kind === "candidate") return candidateRepeater.itemAt(row.sectionIndex)
    if (row.kind === "node") return nodeRepeater.itemAt(row.sectionIndex)
    if (row.kind === "agent") return agentRepeater.itemAt(row.sectionIndex)
    return automationSection.itemAt(row.sectionIndex)
  }

  function ensureSelectionVisible() {
    var delegate = rowDelegate(selectedRow)
    if (!delegate) return
    var top = delegate.mapToItem(contentColumn, 0, 0).y
    var bottom = top + delegate.height
    if (top < panelFlick.contentY) panelFlick.contentY = top
    else if (bottom > panelFlick.contentY + panelFlick.height)
      panelFlick.contentY = Math.max(0, bottom - panelFlick.height)
  }

  function activateSelection() {
    if (selectedRow && selectedRow.kind === "candidate" && !verifyingCandidate)
      candidateVerificationRequested(selectedRow.key)
  }


  function signalColor(tone) {
    return Logic.signalColor(tone, foreground, accent, urgent, dim, healthy, warning)
  }

  onRowsChanged: reconcileRows()
  Component.onCompleted: reconcileRows()

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
      else if (text === "r" || text === "R") root.refreshRequested()
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
          height: Style.space(56)

          ClawMark {
            id: panelClaw
            anchors.left: parent.left
            anchors.top: parent.top
            width: Style.space(20)
            height: width
            color: root.foreground
          }

          Text {
            anchors.left: panelClaw.right
            anchors.leftMargin: Style.space(8)
            anchors.top: parent.top
            anchors.right: gatewayStatus.left
            anchors.rightMargin: Style.space(8)
            text: "OpenClaw"
            elide: Text.ElideRight
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.title
            font.bold: true
          }

          Row {
            id: gatewayStatus
            anchors.right: parent.right
            anchors.top: parent.top
            spacing: Style.space(5)

            SignalPoint {
              anchors.verticalCenter: parent.verticalCenter
              kind: root.gatewaySignal.shape
              color: root.signalColor(root.gatewaySignal.tone)
            }

            Text {
              text: root.gatewaySignal.label
              color: root.signalColor(root.gatewaySignal.tone)
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              font.bold: true
            }
          }

          Text {
            anchors.left: parent.left
            anchors.right: observedTime.left
            anchors.rightMargin: Style.space(8)
            anchors.bottom: parent.bottom
            text: root.summary
            elide: Text.ElideRight
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }

          Text {
            id: observedTime
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            text: root.historical
              ? "Last known " + Logic.relativeTime(root.observedAt, root.nowMs)
              : root.snapshot ? Logic.relativeTime(root.snapshot.generatedAt, root.nowMs) : ""
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }
        }

        Text {
          visible: root.setupVisible
          width: parent.width
          text: "GATEWAY SETUP REQUIRED"
          color: root.accent
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          font.bold: true
        }

        Text {
          visible: root.setupVisible
          width: parent.width
          text: root.snapshot && root.snapshot.setup
            ? String(root.snapshot.setup.guidance || "")
            : "Connect Tailscale on this device, then refresh to find Gateway candidates."
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
          wrapMode: Text.Wrap
        }

        Text {
          visible: root.setupVisible && root.snapshot && root.snapshot.setup
            && !!root.snapshot.setup.error
          width: parent.width
          text: visible ? String(root.snapshot.setup.error) : ""
          color: root.state === "configuration_error" ? root.urgent : root.accent
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          font.bold: true
          wrapMode: Text.Wrap
        }

        Text {
          visible: root.configurationErrorVisible && !root.setupVisible
          width: parent.width
          text: Logic.configurationGuidance(root.state)
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
          wrapMode: Text.Wrap
        }

        Repeater {
          id: candidateRepeater
          model: root.candidates

          delegate: Rectangle {
            id: candidateRow
            required property var modelData
            required property int index
            readonly property var row: root.rows[index]
            readonly property bool selected: !!row && root.selectedKey === row.key
            width: contentColumn.width
            height: Style.space(40)
            radius: Style.cornerRadius
            color: selected ? Style.selectedFillFor(root.foreground, root.accent) : "transparent"
            border.width: selected ? 1 : 0
            border.color: root.accent

            MouseArea {
              anchors.fill: parent
              enabled: !root.verifyingCandidate
              onClicked: {
                root.selectRow(candidateRow.row)
                root.activateSelection()
              }
            }

            Text {
              anchors.left: parent.left
              anchors.leftMargin: Style.space(9)
              anchors.right: candidateAction.left
              anchors.rightMargin: Style.space(8)
              anchors.verticalCenter: parent.verticalCenter
              text: candidateRow.modelData.name
              elide: Text.ElideRight
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.body
              font.bold: true
            }

            Text {
              id: candidateAction
              anchors.right: parent.right
              anchors.rightMargin: Style.space(9)
              anchors.verticalCenter: parent.verticalCenter
              text: root.verifyingCandidate && candidateRow.selected ? "Verifying…" : "Verify"
              color: root.accent
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              font.bold: true
            }
          }
        }

        Text {
          visible: !root.setupVisible && !root.configurationErrorVisible
          width: parent.width
          text: "FLEET"
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          font.bold: true
        }

        Text {
          visible: root.state === "degraded" && root.snapshot
            && root.snapshot.fleet && !root.snapshot.fleet.available
          width: parent.width
          text: "Node metadata unavailable"
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
        }

        Text {
          visible: root.metadata && root.metadata.fleet
            && root.metadata.fleet.available && root.nodes.length === 0
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
            readonly property var row: root.rows[root.candidates.length + index]
            readonly property bool selected: !!row && root.selectedKey === row.key
            readonly property bool offline: modelData.state === "offline"
            readonly property var signal: Logic.nodeSignalPresentation(modelData.state)
            readonly property bool showStatus: Logic.showNodeStatusLabel(modelData.state, root.historical)
            width: contentColumn.width
            height: nodeSummary.height + (selected ? nodeDetail.implicitHeight : 0)
            radius: Style.cornerRadius
            opacity: root.historical ? 0.55 : 1
            color: selected ? Style.selectedFillFor(root.foreground, root.accent) : "transparent"
            border.width: selected ? 1 : 0
            border.color: root.accent
            Accessible.name: modelData.name
            Accessible.description: root.historical ? "Last known" : signal.label

            Item {
              id: nodeSummary
              width: parent.width
              height: Style.space(40)

              MouseArea {
                anchors.fill: parent
                onClicked: root.selectRow(nodeRow.row)
              }

              SignalPoint {
                anchors.left: parent.left
                anchors.leftMargin: Style.space(9)
                anchors.verticalCenter: nodeTitle.verticalCenter
                kind: nodeRow.signal.shape
                color: root.signalColor(nodeRow.signal.tone)
              }

              Text {
                id: nodeTitle
                anchors.left: parent.left
                anchors.leftMargin: Style.space(26)
                anchors.right: nodeRow.showStatus ? nodeState.left : parent.right
                anchors.rightMargin: Style.space(8)
                anchors.verticalCenter: parent.verticalCenter
                text: nodeRow.modelData.name
                elide: Text.ElideRight
                color: nodeRow.offline ? root.dim : root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                font.bold: !nodeRow.offline
              }

              Text {
                id: nodeState
                visible: nodeRow.showStatus
                anchors.right: parent.right
                anchors.rightMargin: Style.space(8)
                anchors.verticalCenter: nodeTitle.verticalCenter
                text: root.historical ? "Last known" : nodeRow.signal.label
                color: root.historical ? root.dim : root.signalColor(nodeRow.signal.tone)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
            }

            NodeDetailCard {
              id: nodeDetail
              visible: nodeRow.selected
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.top: nodeSummary.bottom
              height: implicitHeight
              node: nodeRow.modelData
              observedAt: nodeRow.row ? nodeRow.row.observedAt : ""
              historical: root.historical
              nowMs: root.nowMs
              foreground: root.foreground
              dim: root.dim
              fontFamily: root.fontFamily
            }
          }
        }

        Text {
          visible: !root.setupVisible && !root.configurationErrorVisible
            && (root.agents.length > 0 || (root.state === "degraded" && root.snapshot
              && root.snapshot.agents && !root.snapshot.agents.available))
          width: parent.width
          topPadding: Style.space(8)
          text: "AGENTS"
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          font.bold: true
        }

        Text {
          visible: root.state === "degraded" && root.snapshot
            && root.snapshot.agents && !root.snapshot.agents.available
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
            readonly property var row: root.rows[root.candidates.length + root.nodes.length + index]
            readonly property bool selected: !!row && root.selectedKey === row.key
            readonly property var signal: Logic.signalPresentation(modelData.activity)
            readonly property bool showActivityText: root.historical || modelData.activity !== "idle"
            width: contentColumn.width
            height: agentSummary.height + (selected ? agentDetail.implicitHeight : 0)
            radius: Style.cornerRadius
            opacity: root.historical ? 0.55 : 1
            color: selected ? Style.selectedFillFor(root.foreground, root.accent) : "transparent"
            border.width: selected ? 1 : 0
            border.color: root.accent
            Accessible.name: modelData.name
            Accessible.description: root.historical ? "Last known" : signal.label

            Item {
              id: agentSummary
              width: parent.width
              height: Style.space(48)

              MouseArea {
                anchors.fill: parent
                onClicked: root.selectRow(agentRow.row)
              }

              SignalPoint {
                anchors.left: parent.left
                anchors.leftMargin: Style.space(9)
                anchors.verticalCenter: agentName.verticalCenter
                kind: agentRow.signal.shape
                color: root.signalColor(agentRow.signal.tone)
              }

              Text {
                id: agentName
                anchors.left: parent.left
                anchors.leftMargin: Style.space(26)
                anchors.right: agentRow.showActivityText ? agentActivity.left : parent.right
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
                visible: agentRow.showActivityText
                anchors.right: parent.right
                anchors.rightMargin: Style.space(8)
                anchors.verticalCenter: agentName.verticalCenter
                text: root.historical ? "Last known" : agentRow.signal.label
                color: root.historical ? root.dim : root.signalColor(agentRow.signal.tone)
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
                font.bold: !!agentRow.modelData.taskResult
                  && agentRow.modelData.taskResult.state === "failed"
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
            }

            AgentDetailCard {
              id: agentDetail
              visible: agentRow.selected
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.top: agentSummary.bottom
              height: implicitHeight
              agent: agentRow.modelData
              observedAt: agentRow.row ? agentRow.row.observedAt : ""
              historical: root.historical
              nowMs: root.nowMs
              foreground: root.foreground
              dim: root.dim
              urgent: root.urgent
              fontFamily: root.fontFamily
            }
          }
        }

        AutomationSection {
          id: automationSection
          width: parent.width
          visible: !root.setupVisible && !root.configurationErrorVisible
          section: root.metadata ? root.metadata.automations : null
          automations: root.automations
          rows: root.rows
          rowOffset: root.candidates.length + root.nodes.length + root.agents.length
          selectedKey: root.selectedKey
          nowMs: root.nowMs
          foreground: root.foreground
          dim: root.dim
          accent: root.accent
          urgent: root.urgent
          fontFamily: root.fontFamily
          historical: root.historical
          signalColor: root.signalColor
          showUnavailable: root.state === "degraded"
          onRowSelected: function(row) {
            root.selectRow(row)
          }
        }

      }
    }
  }
}
