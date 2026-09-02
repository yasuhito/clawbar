pragma ComponentBehavior: Bound

import QtQuick
import qs.Commons

// Renders one section of Operational Rows. Every row — Gateway candidate,
// Node, Registered Agent, or Automation — is the same selectable summary
// with an expandable detail beneath it; selection follows the row's key,
// never a positional offset.
Item {
  id: root

  required property var rows
  required property var rowPalette
  required property string selectedKey
  required property double nowMs
  required property bool motionEnabled
  required property int fadeDuration
  required property int expandDuration
  // Shown in the selected action row's right slot instead of its base label.
  property string activeActionLabel: ""
  property bool interactive: true
  // Horizontal inset of the signal dot; Automations sit one unit tighter.
  property int dotInsetUnits: 9
  // Right-edge inset of the status/action slot.
  property int edgeInsetUnits: 8

  signal rowActivated(var vm)
  signal selectionGeometryChanged

  height: rowsColumn.implicitHeight

  function dynamicMember(object, name, fallback) {
    return object && name in object ? object[name] : fallback;
  }

  function itemForKey(key) {
    for (var i = 0; i < repeater.count; i++) {
      var delegate = repeater.itemAt(i);
      var delegateModel = dynamicMember(delegate, "modelData", null);
      if (delegateModel && delegateModel.key === key)
        return delegate;
    }
    return null;
  }

  Column {
    id: rowsColumn
    anchors.left: parent.left
    anchors.right: parent.right
    spacing: Style.space(4)

    Repeater {
      id: repeater
      model: root.rows

      delegate: Rectangle {
        id: rowRoot
        required property var modelData
        readonly property var dot: modelData.dot ? modelData.dot : {
          shape: "circle",
          tone: "muted"
        }
        readonly property bool selected: root.selectedKey !== "" && modelData.key === root.selectedKey
        width: parent.width
        height: summaryArea.height + detailReveal.height
        radius: Style.cornerRadius
        clip: true
        opacity: modelData.historical && !selected ? 0.55 : 1
        color: selected ? Style.selectedFillFor(root.rowPalette.foreground, root.rowPalette.accent) : "transparent"
        border.width: selected ? 1 : 0
        border.color: root.rowPalette.accent
        Accessible.name: modelData.name
        Accessible.description: modelData.accessibleDescription
        onHeightChanged: {
          if (selected)
            root.selectionGeometryChanged();
        }

        Item {
          id: summaryArea
          width: parent.width
          height: Style.space(rowRoot.modelData.hasSub ? 48 : 40)

          MouseArea {
            anchors.fill: parent
            enabled: root.interactive
            onClicked: root.rowActivated(rowRoot.modelData)
          }

          SignalPoint {
            visible: rowRoot.modelData.dot !== null
            anchors.left: parent.left
            anchors.leftMargin: Style.space(root.dotInsetUnits)
            anchors.verticalCenter: titleText.verticalCenter
            kind: rowRoot.dot.shape
            color: rowRoot.selected ? root.rowPalette.selectedSignalColor(rowRoot.dot.tone) : root.rowPalette.signalColor(rowRoot.dot.tone)
          }

          Text {
            id: titleText
            textFormat: Text.PlainText
            anchors.left: parent.left
            anchors.leftMargin: Style.space(rowRoot.modelData.dot !== null ? 26 : 9)
            anchors.right: statusText.visible ? statusText.left : parent.right
            anchors.rightMargin: Style.space(8)
            anchors.top: rowRoot.modelData.hasSub ? parent.top : undefined
            anchors.topMargin: Style.space(6)
            anchors.verticalCenter: rowRoot.modelData.hasSub ? undefined : parent.verticalCenter
            text: rowRoot.modelData.name
            elide: Text.ElideRight
            color: rowRoot.modelData.titleMuted ? (rowRoot.selected ? root.rowPalette.selectedDim : root.rowPalette.dim) : root.rowPalette.foreground
            font.family: root.rowPalette.fontFamily
            font.pixelSize: Style.fontToken("body", Style.fontPx(1.0))
            font.bold: rowRoot.modelData.titleBold
          }

          Text {
            id: subText
            visible: rowRoot.modelData.hasSub
            textFormat: Text.PlainText
            anchors.left: titleText.left
            anchors.right: parent.right
            anchors.rightMargin: Style.space(8)
            anchors.bottom: parent.bottom
            anchors.bottomMargin: Style.space(6)
            text: rowRoot.modelData.subText(root.nowMs)
            elide: Text.ElideRight
            color: rowRoot.modelData.subCritical ? (rowRoot.selected ? root.rowPalette.selectedSignalColor("critical") : root.rowPalette.signalColor("critical")) : (rowRoot.selected ? root.rowPalette.selectedDim : root.rowPalette.dim)
            font.bold: rowRoot.modelData.subCritical
            font.family: root.rowPalette.fontFamily
            font.pixelSize: Style.fontToken("caption", Style.fontPx(0.833))
          }

          Text {
            id: statusText
            visible: rowRoot.modelData.showStatusLabel
            textFormat: Text.PlainText
            anchors.right: parent.right
            anchors.rightMargin: Style.space(root.edgeInsetUnits)
            anchors.verticalCenter: titleText.verticalCenter
            width: rowRoot.modelData.statusCapRatio !== null ? Math.min(implicitWidth, parent.width * rowRoot.modelData.statusCapRatio) : implicitWidth
            horizontalAlignment: rowRoot.modelData.statusCapRatio !== null ? Text.AlignRight : Text.AlignLeft
            text: rowRoot.modelData.statusStyle === "action" && rowRoot.selected && root.activeActionLabel !== "" ? root.activeActionLabel : rowRoot.modelData.statusLabel
            elide: Text.ElideRight
            color: rowRoot.modelData.statusStyle === "action" ? root.rowPalette.accent : rowRoot.selected ? root.rowPalette.selectedSignalColor(rowRoot.dot.tone) : rowRoot.modelData.historical ? root.rowPalette.dim : root.rowPalette.signalColor(rowRoot.dot.tone)
            font.family: root.rowPalette.fontFamily
            font.pixelSize: Style.fontToken("caption", Style.fontPx(0.833))
            font.bold: rowRoot.modelData.statusStyle === "action"
          }
        }

        DetailReveal {
          id: detailReveal
          width: parent.width
          expanded: rowRoot.selected && rowRoot.modelData.detail.length > 0
          contentHeight: cardLoader.active && cardLoader.item ? root.dynamicMember(cardLoader.item, "implicitHeight", 0) : 0
          motionEnabled: root.motionEnabled
          fadeDuration: root.fadeDuration
          expandDuration: root.expandDuration

          Component {
            id: detailCardComponent

            DetailCard {
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.top: parent.top
              vm: rowRoot.modelData
              rowPalette: root.rowPalette
              nowMs: root.nowMs
            }
          }

          Loader {
            id: cardLoader
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            active: rowRoot.modelData.detail.length > 0 && (rowRoot.selected || detailReveal.height > 0)
            sourceComponent: detailCardComponent
          }
        }
      }
    }
  }
}
