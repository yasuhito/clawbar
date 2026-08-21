import QtQuick
import qs.Commons
import qs.Ui
import "ClawbarLogic.js" as Logic

KeyboardPanel {
  id: root

  required property var snapshot
  property double nowMs: Date.now()
  property string summary: ""
  property string selectedKey: ""
  property int selectedIndexHint: 0
  property var expandedKeys: ({})

  signal refreshRequested()

  readonly property var rows: Logic.panelRows(snapshot)
  readonly property var nodes: Logic.fleetNodes(snapshot)
  readonly property var agents: Logic.agents(snapshot)
  readonly property int selectedIndex: Logic.indexForKey(rows, selectedKey)
  readonly property var selectedRow: selectedIndex >= 0 ? rows[selectedIndex] : null
  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color dim: Color.muted
  readonly property color accent: Color.accent
  readonly property color urgent: bar ? bar.urgent : Color.urgent
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family

  focusTarget: keyCatcher
  contentWidth: fittedContentWidth(Style.space(360))
  contentHeight: fittedContentHeight(contentColumn.implicitHeight, Style.space(560))

  function reconcileRows() {
    var selection = Logic.reconcileSelection(rows, selectedKey, selectedIndexHint)
    selectedKey = selection.key
    selectedIndexHint = selection.index < 0 ? 0 : selection.index
    expandedKeys = Logic.reconcileExpanded(rows, expandedKeys)
  }

  function selectRow(row) {
    if (!row) return
    selectedKey = row.key
    selectedIndexHint = Logic.indexForKey(rows, row.key)
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
    return row.kind === "node"
      ? nodeRepeater.itemAt(row.sectionIndex)
      : agentRepeater.itemAt(row.sectionIndex)
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
    if (!selectedRow || !selectedRow.expandable) return
    var next = Object.assign({}, expandedKeys)
    next[selectedRow.key] = !next[selectedRow.key]
    expandedKeys = next
    Qt.callLater(root.ensureSelectionVisible)
  }

  function stateColor(value) {
    if (value === "offline" || value === "configuration_error") return urgent
    if (value === "healthy") return accent
    return dim
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
            text: root.snapshot ? Logic.relativeTime(root.snapshot.generatedAt, root.nowMs) : ""
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
          visible: root.snapshot && root.snapshot.fleet && !root.snapshot.fleet.available
          width: parent.width
          text: "Node metadata unavailable"
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
        }

        Text {
          visible: root.snapshot && root.snapshot.fleet
            && root.snapshot.fleet.available && root.nodes.length === 0
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
            readonly property var row: root.rows[index]
            readonly property bool selected: !!row && root.selectedKey === row.key
            readonly property bool expanded: !!row && !!root.expandedKeys[row.key]
            width: contentColumn.width
            height: Style.space(expanded ? 72 : 48)
            radius: Style.cornerRadius
            color: selected ? Style.selectedFillFor(root.foreground, root.accent) : "transparent"
            border.width: selected ? 1 : 0
            border.color: root.accent

            MouseArea {
              anchors.fill: parent
              onClicked: {
                root.selectRow(nodeRow.row)
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
          visible: root.snapshot && root.snapshot.agents && !root.snapshot.agents.available
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
            readonly property var row: root.rows[root.nodes.length + index]
            readonly property bool selected: !!row && root.selectedKey === row.key
            readonly property string activityText: Logic.activityLabel(modelData.activity)
            width: contentColumn.width
            height: Style.space(48)
            radius: Style.cornerRadius
            color: selected ? Style.selectedFillFor(root.foreground, root.accent) : "transparent"
            border.width: selected ? 1 : 0
            border.color: root.accent

            MouseArea {
              anchors.fill: parent
              onClicked: root.selectRow(agentRow.row)
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
              var absolute = Logic.absoluteLocalTime(root.selectedRow.timestamp)
              return root.selectedRow.typeLabel + " · " + root.selectedRow.item.name
                + (absolute ? "\nObserved " + absolute : "\n" + root.selectedRow.missingTimestampLabel)
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
