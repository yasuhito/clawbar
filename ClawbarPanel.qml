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
  readonly property int selectedIndex: Logic.indexForKey(selectionKeys, selectedKey)
  readonly property var selectedRow: selectedIndex >= 0 ? rows[selectedIndex] : null
  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color panelSurface: Color.popups.background
  readonly property color rawDim: Color.muted
  readonly property color dim: Logic.readableColor(rawDim, foreground, panelSurface, 4.5)
  readonly property color selectedSurface: Logic.blendColor(
    Style.selectedStateColor(foreground, accent), panelSurface, Style.selectedFillAlpha
  )
  readonly property color selectedDim: Logic.readableColor(dim, foreground, selectedSurface, 4.5)
  readonly property color accent: Color.accent
  readonly property color urgent: bar ? bar.urgent : Color.urgent
  required property color healthy
  required property color warning
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property var gatewaySignal: Logic.panelSignal(snapshot, state)

  // One palette object carries every color the Operational Rows need; the
  // panel derives it once so sections never re-thread theme colors.
  readonly property var palette: Logic.makePalette({
    foreground: String(foreground),
    accent: String(accent),
    urgent: String(urgent),
    muted: String(rawDim),
    healthy: String(healthy),
    warning: String(warning),
    panelSurface: String(panelSurface),
    selectedSurface: String(selectedSurface),
    fontFamily: fontFamily
  })
  readonly property var sections: Logic.panelSections(snapshot, state)
  readonly property var selectionKeys: Logic.sectionKeys(sections)

  /* ───────────────────────────────────────────────────────
   * DETAIL REVEAL STORYBOARD
   *
   *    0ms   selection changes → surface and border update
   *    0ms   detail opacity 0 → 1 and height 0 → content
   *  120ms   detail content reaches full opacity
   *  180ms   detail height settles; selected row stays visible
   * ─────────────────────────────────────────────────────── */
  property bool detailMotionEnabled: true
  readonly property int detailFadeDuration: 120
  readonly property int detailExpandDuration: 180

  /* ───────────────────────────────────────────────────────
   * SCROLL INDICATOR STORYBOARD
   *
   *    0ms   content moves → thumb becomes clear
   *  850ms   movement settles → thumb starts fading
   * 1010ms   thumb reaches its quiet resting opacity
   * ─────────────────────────────────────────────────────── */
  readonly property int scrollIndicatorSettleDelay: 850
  readonly property int scrollIndicatorFadeDuration: 160
  readonly property real scrollIndicatorActiveOpacity: 0.68
  readonly property real scrollIndicatorIdleOpacity: 0.26
  readonly property int scrollIndicatorWidth: Style.space(2)
  readonly property int scrollIndicatorMinHeight: Style.space(28)
  readonly property real scrollProgress: panelFlick.contentHeight > panelFlick.height
    ? Math.max(0, Math.min(1,
      panelFlick.contentY / (panelFlick.contentHeight - panelFlick.height)))
    : 0

  focusTarget: keyCatcher
  contentWidth: fittedContentWidth(Style.space(360))
  contentHeight: fittedContentHeight(
    panelHeader.height + Style.space(4) + contentColumn.implicitHeight,
    Style.space(560)
  )

  function reconcileRows() {
    var selection = Logic.reconcileSelection(selectionKeys, selectedKey, selectedIndexHint)
    selectedKey = selection.key
    selectedIndexHint = selection.index < 0 ? 0 : selection.index
  }

  function selectRow(row) {
    if (!row) return
    selectedKey = row.key
    selectedIndexHint = Logic.indexForKey(selectionKeys, row.key)
    Qt.callLater(root.ensureSelectionVisible)
  }

  function moveSelection(delta) {
    var next = Logic.moveFocus(selectedIndex, selectionKeys.length, delta)
    if (next < 0) return
    selectedKey = rows[next].key
    selectedIndexHint = next
    Qt.callLater(root.ensureSelectionVisible)
  }

  function rowDelegate(row) {
    if (!row) return null
    if (row.kind === "candidate") return candidateRepeater.itemAt(row.sectionIndex)
    return null
  }

  // Migrated kinds live in key-addressable RowSections; the rest keep the
  // legacy offset lookup until their migration step.
  function sectionForKind(kind) {
    if (kind === "automation") return automationRows
    if (kind === "node") return nodeRows
    if (kind === "agent") return agentRows
    return null
  }

  function delegateForSelection() {
    var kind = selectedRow ? selectedRow.kind : ""
    var section = sectionForKind(kind)
    if (section) return section.itemForKey(selectedKey)
    return rowDelegate(selectedRow)
  }

  function ensureSelectionVisible() {
    var delegate = delegateForSelection()
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
    var preferred = Logic.signalColor(tone, foreground, accent, urgent, dim, healthy, warning)
    return Logic.readableColor(preferred, foreground, panelSurface, 4.5)
  }

  function selectedSignalColor(tone) {
    var preferred = Logic.signalColor(tone, foreground, accent, urgent, dim, healthy, warning)
    return Logic.readableColor(preferred, foreground, selectedSurface, 4.5)
  }

  onRowsChanged: reconcileRows()
  Component.onCompleted: reconcileRows()

  PanelKeyCatcher {
    id: keyCatcher
    anchors.fill: parent

    Timer {
      id: scrollIndicatorActivity
      interval: root.scrollIndicatorSettleDelay
      repeat: false
    }

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

    Item {
      id: panelHeader
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.top: parent.top
      height: Style.space(60)

      ClawMark {
        id: panelClaw
        anchors.left: parent.left
        anchors.top: parent.top
        width: Style.space(20)
        height: width
        color: root.foreground
      }

      Text {
        textFormat: Text.PlainText
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
          textFormat: Text.PlainText
          text: root.gatewaySignal.label
          color: root.signalColor(root.gatewaySignal.tone)
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          font.bold: true
        }
      }

      Text {
        textFormat: Text.PlainText
        anchors.left: parent.left
        anchors.right: observedTime.left
        anchors.rightMargin: Style.space(8)
        anchors.bottom: headerDivider.top
        anchors.bottomMargin: Style.space(4)
        text: root.summary
        elide: Text.ElideRight
        color: root.dim
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
      }

      Text {
        textFormat: Text.PlainText
        id: observedTime
        anchors.right: parent.right
        anchors.bottom: headerDivider.top
        anchors.bottomMargin: Style.space(4)
        text: root.historical
          ? "Last known " + Logic.relativeTime(root.observedAt, root.nowMs)
          : root.snapshot ? Logic.relativeTime(root.snapshot.generatedAt, root.nowMs) : ""
        color: root.dim
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
      }

      Rectangle {
        id: headerDivider
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 1
        color: root.dim
        opacity: 0.28
      }
    }

    Flickable {
      id: panelFlick
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.top: panelHeader.bottom
      anchors.topMargin: Style.space(4)
      anchors.bottom: parent.bottom
      contentWidth: width
      contentHeight: contentColumn.implicitHeight
      clip: true
      boundsBehavior: Flickable.StopAtBounds
      flickableDirection: Flickable.VerticalFlick
      interactive: contentHeight > height
      onContentYChanged: {
        if (interactive) scrollIndicatorActivity.restart()
      }

      Column {
        id: contentColumn
        width: panelFlick.width - Style.space(8)
        spacing: Style.space(4)

        Text {
          textFormat: Text.PlainText
          visible: root.setupVisible
          width: parent.width
          text: "GATEWAY SETUP REQUIRED"
          color: root.accent
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          font.bold: true
        }

        Text {
          textFormat: Text.PlainText
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
          textFormat: Text.PlainText
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
          textFormat: Text.PlainText
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
              textFormat: Text.PlainText
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
              textFormat: Text.PlainText
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
          textFormat: Text.PlainText
          visible: !root.setupVisible && !root.configurationErrorVisible
          width: parent.width
          text: "FLEET"
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          font.bold: true
        }

        Text {
          textFormat: Text.PlainText
          visible: root.state === "degraded" && root.snapshot
            && root.snapshot.fleet && !root.snapshot.fleet.available
          width: parent.width
          text: Logic.metadataUnavailableText(root.snapshot && root.snapshot.fleet)
            || "Node metadata unavailable"
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
        }

        Text {
          textFormat: Text.PlainText
          visible: root.metadata && root.metadata.fleet
            && root.metadata.fleet.available && root.nodes.length === 0
          width: parent.width
          text: "Empty Fleet"
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
        }

        Component {
          id: nodeDetailDelegate
          NodeDetailCard {}
        }

        RowSection {
          id: nodeRows
          width: parent.width
          rows: Logic.sectionRows(root.sections, "node")
          palette: root.palette
          selectedKey: root.selectedKey
          nowMs: root.nowMs
          historical: root.historical
          motionEnabled: root.detailMotionEnabled
          fadeDuration: root.detailFadeDuration
          expandDuration: root.detailExpandDuration
          detailComponent: nodeDetailDelegate
          onRowActivated: function(vm) {
            if (!vm.key) return
            root.selectRow(vm)
          }
          onSelectionGeometryChanged: Qt.callLater(root.ensureSelectionVisible)
        }

        Text {
          textFormat: Text.PlainText
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
          textFormat: Text.PlainText
          visible: root.state === "degraded" && root.snapshot
            && root.snapshot.agents && !root.snapshot.agents.available
          width: parent.width
          text: Logic.metadataUnavailableText(root.snapshot && root.snapshot.agents)
            || "Agent and Task metadata unavailable"
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
        }

        Component {
          id: agentDetailDelegate
          AgentDetailCard {}
        }

        RowSection {
          id: agentRows
          width: parent.width
          rows: Logic.sectionRows(root.sections, "agent")
          palette: root.palette
          selectedKey: root.selectedKey
          nowMs: root.nowMs
          historical: root.historical
          motionEnabled: root.detailMotionEnabled
          fadeDuration: root.detailFadeDuration
          expandDuration: root.detailExpandDuration
          detailComponent: agentDetailDelegate
          onRowActivated: function(vm) {
            if (!vm.key) return
            root.selectRow(vm)
          }
          onSelectionGeometryChanged: Qt.callLater(root.ensureSelectionVisible)
        }

        Text {
          textFormat: Text.PlainText
          visible: !root.setupVisible && !root.configurationErrorVisible
          width: parent.width
          topPadding: Style.space(8)
          text: "AUTOMATIONS"
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          font.bold: true
        }

        Text {
          textFormat: Text.PlainText
          visible: !root.setupVisible && !root.configurationErrorVisible
            && root.state === "degraded" && root.snapshot
            && root.snapshot.automations && !root.snapshot.automations.available
          width: parent.width
          text: root.snapshot && root.snapshot.automations
            && root.snapshot.automations.reason === "more_than_500"
              ? "Unavailable — more than 500 Automations"
              : "Unavailable"
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
        }

        Text {
          textFormat: Text.PlainText
          visible: !root.setupVisible && !root.configurationErrorVisible
            && !!root.metadata && root.metadata.automations
            && root.metadata.automations.available && root.automations.length === 0
          width: parent.width
          text: "No Automations"
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
        }

        Component {
          id: automationDetailDelegate
          AutomationDetailCard {}
        }

        RowSection {
          id: automationRows
          width: parent.width
          visible: !root.setupVisible && !root.configurationErrorVisible
          rows: Logic.sectionRows(root.sections, "automation")
          palette: root.palette
          selectedKey: root.selectedKey
          nowMs: root.nowMs
          historical: root.historical
          motionEnabled: root.detailMotionEnabled
          fadeDuration: root.detailFadeDuration
          expandDuration: root.detailExpandDuration
          detailComponent: automationDetailDelegate
          dotInsetUnits: 8
          onRowActivated: function(vm) {
            if (!vm.key) return
            root.selectRow(vm)
          }
          onSelectionGeometryChanged: Qt.callLater(root.ensureSelectionVisible)
        }

      }
    }

    Rectangle {
      id: scrollIndicator
      readonly property bool active: panelFlick.moving || panelFlick.dragging
        || scrollIndicatorActivity.running
      visible: panelFlick.contentHeight > panelFlick.height + 1
      width: root.scrollIndicatorWidth
      height: Math.max(
        root.scrollIndicatorMinHeight,
        panelFlick.height * Math.min(1, panelFlick.height / panelFlick.contentHeight)
      )
      x: panelFlick.x + panelFlick.width - width
      y: panelFlick.y + root.scrollProgress * Math.max(0, panelFlick.height - height)
      radius: width / 2
      color: root.foreground
      opacity: active
        ? root.scrollIndicatorActiveOpacity
        : root.scrollIndicatorIdleOpacity
      z: 2
      Accessible.ignored: true

      Behavior on opacity {
        NumberAnimation {
          duration: root.scrollIndicatorFadeDuration
          easing.type: Easing.OutCubic
        }
      }
    }
  }
}
