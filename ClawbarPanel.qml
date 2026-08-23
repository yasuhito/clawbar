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
  required property bool automationHistoryBusy

  signal automationHistoryRequested(string automationId)
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
    if (selectedRow && selectedRow.kind === "automation" && selectedCard.visible) {
      var cardTop = selectedCard.mapToItem(contentColumn, 0, 0).y
      bottom = Math.max(bottom, cardTop + selectedCard.height)
    }
    if (top < panelFlick.contentY) panelFlick.contentY = top
    else if (bottom > panelFlick.contentY + panelFlick.height)
      panelFlick.contentY = Math.max(0, bottom - panelFlick.height)
  }

  function requestAutomationHistory() {
    if (selectedRow && selectedRow.kind === "automation" && !automationHistoryBusy)
      automationHistoryRequested(selectedRow.item.id)
  }

  function activateSelection() {
    if (!selectedRow) return
    if (selectedRow.kind === "candidate" && !verifyingCandidate)
      candidateVerificationRequested(selectedRow.key)
    else
      requestAutomationHistory()
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
      else if (text === "o" || text === "O") root.requestAutomationHistory()
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
            width: contentColumn.width
            height: Style.space(40)
            radius: Style.cornerRadius
            opacity: root.historical ? 0.55 : 1
            color: selected ? Style.selectedFillFor(root.foreground, root.accent) : "transparent"
            border.width: selected ? 1 : 0
            border.color: root.accent

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
              anchors.right: nodeState.left
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
              anchors.right: parent.right
              anchors.rightMargin: Style.space(8)
              anchors.verticalCenter: nodeTitle.verticalCenter
              text: root.historical ? "Last known" : nodeRow.signal.label
              color: root.historical ? root.dim : root.signalColor(nodeRow.signal.tone)
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
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
            width: contentColumn.width
            height: Style.space(48)
            radius: Style.cornerRadius
            opacity: root.historical ? 0.55 : 1
            color: selected ? Style.selectedFillFor(root.foreground, root.accent) : "transparent"
            border.width: selected ? 1 : 0
            border.color: root.accent

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

        Rectangle {
          id: selectedCard
          visible: root.selectedRow !== null
          width: parent.width
          height: selectedDetail.implicitHeight + Style.space(16)
            + (historyButton.visible ? historyButton.height + Style.space(8) : 0)
          radius: Style.cornerRadius
          color: Style.selectedFillFor(root.foreground, Color.popups.background)

          Text {
            id: selectedDetail
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: Style.space(8)
            text: {
              if (!root.selectedRow) return ""
              var prefix = root.selectedRow.historical
                ? "Last known · " + Logic.relativeTime(root.selectedRow.observedAt, root.nowMs) + "\n"
                : ""
              if (root.selectedRow.kind === "candidate")
                return "Gateway candidate · " + root.selectedRow.item.name
                  + (root.verifyingCandidate ? "\nVerifying supported read-only Gateway JSON…" : "\nPress Enter to verify")
              if (root.selectedRow.kind === "automation") {
                var automation = root.selectedRow.item
                var automationLines = ["Automation · " + automation.name]
                automationLines.push(
                  Logic.automationKindLabel(automation.kind)
                    + " · " + Logic.automationStatusLabel(automation)
                )
                var nextRun = Logic.absoluteLocalTime(automation.nextRunAt)
                var lastRun = Logic.absoluteLocalTime(automation.lastRunAt)
                if (nextRun) automationLines.push("Next run " + nextRun)
                if (lastRun) automationLines.push("Last run " + lastRun)
                if (!nextRun && !lastRun && automation.lastResult === "none")
                  automationLines.push("No run timestamps")
                return prefix + automationLines.join("\n")
              }
              var absolute = Logic.absoluteLocalTime(root.selectedRow.timestamp)
              var heading = prefix + root.selectedRow.typeLabel + " · " + root.selectedRow.item.name
              var observation = absolute
                ? "Observed " + absolute
                : root.selectedRow.missingTimestampLabel
              if (root.selectedRow.kind === "node")
                return [heading, Logic.nodeMetadataLabel(root.selectedRow.item), observation].join("\n")
              return heading + "\n" + observation
            }
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            wrapMode: Text.Wrap
          }

          Button {
            id: historyButton
            visible: root.selectedRow !== null && root.selectedRow.kind === "automation"
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.margins: Style.space(8)
            text: root.automationHistoryBusy ? "Opening…" : "View run history"
            enabled: !root.automationHistoryBusy
            foreground: root.foreground
            accent: root.accent
            fontFamily: root.fontFamily
            fontSize: Style.font.caption
            bordered: true
            onClicked: root.requestAutomationHistory()
          }
        }

      }
    }
  }
}
