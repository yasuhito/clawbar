import QtQuick
import qs.Commons
import qs.Ui

// Renders one section of Operational Rows. Every row — Gateway candidate,
// Node, Registered Agent, or Automation — is the same selectable summary
// with an expandable detail beneath it; selection follows the row's key,
// never a positional offset.
Item {
  id: root

  required property var rows
  required property var palette
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

  function itemForKey(key) {
    for (var i = 0; i < repeater.count; i++) {
      var delegate = repeater.itemAt(i);
      if (delegate && delegate.modelData.key === key)
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
        color: selected ? Style.selectedFillFor(root.palette.foreground, root.palette.accent) : "transparent"
        border.width: selected ? 1 : 0
        border.color: root.palette.accent
        Accessible.name: modelData.name
        Accessible.description: modelData.accessibleDescription
        onHeightChanged: {
          if (selected)
            root.selectionGeometryChanged();
        }

        Item {
          id: summaryArea
          width: parent.width
          height: Style.space(modelData.hasSub ? 48 : 40)

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
            color: rowRoot.selected ? root.palette.selectedSignalColor(rowRoot.dot.tone) : root.palette.signalColor(rowRoot.dot.tone)
          }

          Text {
            id: titleText
            textFormat: Text.PlainText
            anchors.left: parent.left
            anchors.leftMargin: Style.space(modelData.dot !== null ? 26 : 9)
            anchors.right: statusText.visible ? statusText.left : parent.right
            anchors.rightMargin: Style.space(8)
            anchors.top: modelData.hasSub ? parent.top : undefined
            anchors.topMargin: Style.space(6)
            anchors.verticalCenter: modelData.hasSub ? undefined : parent.verticalCenter
            text: modelData.name
            elide: Text.ElideRight
            color: modelData.titleMuted ? (rowRoot.selected ? root.palette.selectedDim : root.palette.dim) : root.palette.foreground
            font.family: root.palette.fontFamily
            font.pixelSize: Style.font.body
            font.bold: modelData.titleBold
          }

          Text {
            id: subText
            visible: modelData.hasSub
            textFormat: Text.PlainText
            anchors.left: titleText.left
            anchors.right: parent.right
            anchors.rightMargin: Style.space(8)
            anchors.bottom: parent.bottom
            anchors.bottomMargin: Style.space(6)
            text: modelData.subText(root.nowMs)
            elide: Text.ElideRight
            color: modelData.subCritical ? (rowRoot.selected ? root.palette.selectedSignalColor("critical") : root.palette.signalColor("critical")) : (rowRoot.selected ? root.palette.selectedDim : root.palette.dim)
            font.bold: modelData.subCritical
            font.family: root.palette.fontFamily
            font.pixelSize: Style.font.caption
          }

          Text {
            id: statusText
            visible: modelData.showStatusLabel
            textFormat: Text.PlainText
            anchors.right: parent.right
            anchors.rightMargin: Style.space(root.edgeInsetUnits)
            anchors.verticalCenter: titleText.verticalCenter
            width: modelData.statusCapRatio !== null ? Math.min(implicitWidth, parent.width * modelData.statusCapRatio) : implicitWidth
            horizontalAlignment: modelData.statusCapRatio !== null ? Text.AlignRight : Text.AlignLeft
            text: modelData.statusStyle === "action" && rowRoot.selected && root.activeActionLabel !== "" ? root.activeActionLabel : modelData.statusLabel
            elide: Text.ElideRight
            color: modelData.statusStyle === "action" ? root.palette.accent : rowRoot.selected ? root.palette.selectedSignalColor(rowRoot.dot.tone) : rowRoot.modelData.historical ? root.palette.dim : root.palette.signalColor(rowRoot.dot.tone)
            font.family: root.palette.fontFamily
            font.pixelSize: Style.font.caption
            font.bold: modelData.statusStyle === "action"
          }
        }

        DetailReveal {
          id: detailReveal
          width: parent.width
          expanded: rowRoot.selected && rowRoot.modelData.detail.length > 0
          contentHeight: cardLoader.active && cardLoader.item ? cardLoader.item.implicitHeight : 0
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
              palette: root.palette
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
