pragma ComponentBehavior: Bound

import QtQuick
import qs.Commons
import qs.Ui
import "ClawbarPresentation.js" as Presentation
import "ClawbarPanelModel.js" as PanelModel
import "ClawbarColor.js" as ColorKit

KeyboardPanel {
  id: root

  required property var panelModel
  required property var gatewaySignal
  property double nowMs: Date.now()
  property string summary: ""
  property string selectedKey: ""
  property int selectedIndexHint: 0
  property bool verifyingCandidate: false

  signal refreshRequested
  signal candidateVerificationRequested(string candidateKey)

  readonly property var sections: panelModel.sections
  readonly property var candidateSection: PanelModel.sectionForKind(sections, "candidate")
  readonly property var fleetSection: PanelModel.sectionForKind(sections, "node")
  readonly property var agentsSection: PanelModel.sectionForKind(sections, "agent")
  readonly property var automationsSection: PanelModel.sectionForKind(sections, "automation")
  readonly property int selectedIndex: Presentation.indexForKey(selectionKeys, selectedKey)
  readonly property string selectedKind: Presentation.keyKind(sections, selectedKey)
  readonly property color foreground: dynamicMember(bar, "foreground", Color.foreground)
  readonly property color panelSurface: Color.composed("popups.background", "popups.background-alpha", Color.background, 1.0)
  readonly property color rawDim: Color.muted
  readonly property color dim: ColorKit.readableColor(rawDim, foreground, panelSurface, 4.5)
  readonly property color selectedSurface: ColorKit.blendColor(Style.selectedStateColor(foreground, accent), panelSurface, Style.selectedFillAlpha)
  readonly property color selectedDim: ColorKit.readableColor(dim, foreground, selectedSurface, 4.5)
  readonly property color accent: Color.accent
  readonly property color urgent: dynamicMember(bar, "urgent", Color.urgent)
  required property color healthy
  required property color warning
  readonly property string fontFamily: dynamicMember(bar, "fontFamily", Style.fontFamily)
  readonly property int captionFontSize: Style.fontToken("caption", Style.fontPx(0.833))
  readonly property int bodyFontSize: Style.fontToken("body", Style.fontPx(1.0))

  // One palette object carries every color the Operational Rows need; the
  // panel derives it once so sections never re-thread theme colors.
  readonly property var palette: ColorKit.makePalette({
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
  readonly property var selectionKeys: Presentation.sectionKeys(sections)

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
  readonly property real scrollProgress: panelFlick.contentHeight > panelFlick.height ? Math.max(0, Math.min(1, panelFlick.contentY / (panelFlick.contentHeight - panelFlick.height))) : 0

  focusTarget: keyCatcher
  contentWidth: fittedContentWidth(Style.space(360))
  contentHeight: fittedContentHeight(panelHeader.height + Style.space(4) + contentColumn.implicitHeight, Style.space(560))

  function dynamicMember(object, name, fallback) {
    return object && name in object ? object[name] : fallback;
  }

  function reconcileRows() {
    var selection = Presentation.reconcileSelection(selectionKeys, selectedKey, selectedIndexHint);
    selectedKey = selection.key;
    selectedIndexHint = selection.index < 0 ? 0 : selection.index;
  }

  function selectRow(row) {
    if (!row)
      return;
    selectedKey = row.key;
    selectedIndexHint = Presentation.indexForKey(selectionKeys, row.key);
    Qt.callLater(root.ensureSelectionVisible);
  }

  function moveSelection(delta) {
    var next = Presentation.moveFocus(selectedIndex, selectionKeys.length, delta);
    if (next < 0)
      return;
    selectedKey = selectionKeys[next];
    selectedIndexHint = next;
    Qt.callLater(root.ensureSelectionVisible);
  }

  // Every kind lives in a key-addressable RowSection.
  function sectionForKind(kind) {
    if (kind === "automation")
      return automationRows;
    if (kind === "node")
      return nodeRows;
    if (kind === "agent")
      return agentRows;
    if (kind === "candidate")
      return candidateRows;
    return null;
  }

  function ensureSelectionVisible() {
    var section = sectionForKind(selectedKind);
    var delegate = section ? section.itemForKey(selectedKey) : null;
    if (!delegate)
      return;
    var top = delegate.mapToItem(contentColumn, 0, 0).y;
    var bottom = top + delegate.height;
    if (top < panelFlick.contentY)
      panelFlick.contentY = top;
    else if (bottom > panelFlick.contentY + panelFlick.height)
      panelFlick.contentY = Math.max(0, bottom - panelFlick.height);
  }

  function activateSelection() {
    if (selectedKind === "candidate" && !verifyingCandidate)
      candidateVerificationRequested(selectedKey);
  }

  onSectionsChanged: reconcileRows()
  Component.onCompleted: reconcileRows()

  PanelKeyCatcher {
    id: keyCatcher
    anchors.fill: parent

    Timer {
      id: scrollIndicatorActivity
      interval: root.scrollIndicatorSettleDelay
      repeat: false
    }

    onMoveRequested: function (dx, dy) {
      if (dy !== 0)
        root.moveSelection(dy);
      else if (dx !== 0)
        root.moveSelection(dx);
    }
    onActivateRequested: root.activateSelection()
    onCloseRequested: root.close()
    onTextKey: function (text) {
      if (text === "j" || text === "J")
        root.moveSelection(1);
      else if (text === "k" || text === "K")
        root.moveSelection(-1);
      else if (text === "r" || text === "R")
        root.refreshRequested();
    }

    PanelHeader {
      id: panelHeader
      rowPalette: root.palette
      gatewaySignal: root.gatewaySignal
      summary: root.summary
      timeCaption: Presentation.panelTimeCaption(root.panelModel, root.nowMs)
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
        if (interactive)
          scrollIndicatorActivity.restart();
      }

      Column {
        id: contentColumn
        width: panelFlick.width - Style.space(8)
        spacing: Style.space(4)

        Text {
          textFormat: Text.PlainText
          visible: root.panelModel.setup.visible
          width: parent.width
          text: root.panelModel.setup.heading
          color: root.accent
          font.family: root.fontFamily
          font.pixelSize: root.captionFontSize
          font.bold: true
        }

        Text {
          textFormat: Text.PlainText
          visible: root.panelModel.setup.visible
          width: parent.width
          text: root.panelModel.setup.guidance
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: root.bodyFontSize
          wrapMode: Text.Wrap
        }

        Text {
          textFormat: Text.PlainText
          visible: root.panelModel.setup.visible && !!root.panelModel.setup.error
          width: parent.width
          text: visible ? root.panelModel.setup.error : ""
          color: root.panelModel.setup.errorCritical ? root.urgent : root.accent
          font.family: root.fontFamily
          font.pixelSize: root.captionFontSize
          font.bold: true
          wrapMode: Text.Wrap
        }

        Text {
          textFormat: Text.PlainText
          visible: root.panelModel.setup.configurationGuidanceVisible
          width: parent.width
          text: root.panelModel.setup.configurationGuidance
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: root.bodyFontSize
          wrapMode: Text.Wrap
        }

        RowSection {
          id: candidateRows
          width: parent.width
          visible: root.candidateSection.visible
          rows: root.candidateSection.rows
          rowPalette: root.palette
          selectedKey: root.selectedKey
          nowMs: root.nowMs
          motionEnabled: root.detailMotionEnabled
          fadeDuration: root.detailFadeDuration
          expandDuration: root.detailExpandDuration
          interactive: !root.verifyingCandidate
          activeActionLabel: root.verifyingCandidate ? "Verifying…" : ""
          edgeInsetUnits: 9
          onRowActivated: function (vm) {
            if (!vm.key)
              return;
            root.selectRow(vm);
            if (!root.verifyingCandidate)
              root.candidateVerificationRequested(vm.key);
          }
          onSelectionGeometryChanged: Qt.callLater(root.ensureSelectionVisible)
        }

        Text {
          textFormat: Text.PlainText
          visible: root.fleetSection.visible
          width: parent.width
          text: root.fleetSection.heading
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: root.captionFontSize
          font.bold: true
        }

        Text {
          textFormat: Text.PlainText
          visible: root.fleetSection.visible && !!root.fleetSection.unavailableText
          width: parent.width
          text: root.fleetSection.unavailableText
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: root.bodyFontSize
        }

        Text {
          textFormat: Text.PlainText
          visible: root.fleetSection.visible && !!root.fleetSection.emptyText
          width: parent.width
          text: root.fleetSection.emptyText
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: root.bodyFontSize
        }

        RowSection {
          id: nodeRows
          width: parent.width
          visible: root.fleetSection.visible
          rows: root.fleetSection.rows
          rowPalette: root.palette
          selectedKey: root.selectedKey
          nowMs: root.nowMs
          motionEnabled: root.detailMotionEnabled
          fadeDuration: root.detailFadeDuration
          expandDuration: root.detailExpandDuration
          onRowActivated: function (vm) {
            if (vm.key)
              root.selectRow(vm);
          }
          onSelectionGeometryChanged: Qt.callLater(root.ensureSelectionVisible)
        }

        Text {
          textFormat: Text.PlainText
          visible: root.agentsSection.visible
          width: parent.width
          topPadding: Style.space(8)
          text: root.agentsSection.heading
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: root.captionFontSize
          font.bold: true
        }

        Text {
          textFormat: Text.PlainText
          visible: root.agentsSection.visible && !!root.agentsSection.unavailableText
          width: parent.width
          text: root.agentsSection.unavailableText
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: root.bodyFontSize
        }

        RowSection {
          id: agentRows
          width: parent.width
          visible: root.agentsSection.visible
          rows: root.agentsSection.rows
          rowPalette: root.palette
          selectedKey: root.selectedKey
          nowMs: root.nowMs
          motionEnabled: root.detailMotionEnabled
          fadeDuration: root.detailFadeDuration
          expandDuration: root.detailExpandDuration
          onRowActivated: function (vm) {
            if (vm.key)
              root.selectRow(vm);
          }
          onSelectionGeometryChanged: Qt.callLater(root.ensureSelectionVisible)
        }

        Text {
          textFormat: Text.PlainText
          visible: root.automationsSection.visible
          width: parent.width
          topPadding: Style.space(8)
          text: root.automationsSection.heading
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: root.captionFontSize
          font.bold: true
        }

        Text {
          textFormat: Text.PlainText
          visible: root.automationsSection.visible && !!root.automationsSection.unavailableText
          width: parent.width
          text: root.automationsSection.unavailableText
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: root.bodyFontSize
        }

        Text {
          textFormat: Text.PlainText
          visible: root.automationsSection.visible && !!root.automationsSection.emptyText
          width: parent.width
          text: root.automationsSection.emptyText
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: root.bodyFontSize
        }

        RowSection {
          id: automationRows
          width: parent.width
          visible: root.automationsSection.visible
          rows: root.automationsSection.rows
          rowPalette: root.palette
          selectedKey: root.selectedKey
          nowMs: root.nowMs
          motionEnabled: root.detailMotionEnabled
          fadeDuration: root.detailFadeDuration
          expandDuration: root.detailExpandDuration
          dotInsetUnits: 8
          onRowActivated: function (vm) {
            if (vm.key)
              root.selectRow(vm);
          }
          onSelectionGeometryChanged: Qt.callLater(root.ensureSelectionVisible)
        }
      }
    }

    Rectangle {
      id: scrollIndicator
      readonly property bool active: panelFlick.moving || panelFlick.dragging || scrollIndicatorActivity.running
      visible: panelFlick.contentHeight > panelFlick.height + 1
      width: root.scrollIndicatorWidth
      height: Math.max(root.scrollIndicatorMinHeight, panelFlick.height * Math.min(1, panelFlick.height / panelFlick.contentHeight))
      x: panelFlick.x + panelFlick.width - width
      y: panelFlick.y + root.scrollProgress * Math.max(0, panelFlick.height - height)
      radius: width / 2
      color: root.foreground
      opacity: active ? root.scrollIndicatorActiveOpacity : root.scrollIndicatorIdleOpacity
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
