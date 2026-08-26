import QtQuick
import qs.Commons
import "ClawbarLogic.js" as Logic

Item {
  id: root

  // Uniform Operational Row detail interface: injected by RowSection's loader.
  required property var vm
  required property var palette
  required property double nowMs
  required property bool historical

  readonly property var node: vm.item
  readonly property string observedAt: vm.observedAt

  implicitHeight: detailColumn.implicitHeight + Style.space(16)

  Column {
    id: detailColumn
    anchors.left: parent.left
    anchors.right: parent.right
    anchors.top: parent.top
    anchors.margins: Style.space(8)
    spacing: Style.space(4)

    Text {
      textFormat: Text.PlainText
      visible: root.historical
      width: parent.width
      text: "Last known · " + Logic.relativeTime(root.observedAt, root.nowMs)
      color: root.palette.selectedDim
      font.family: root.palette.fontFamily
      font.pixelSize: Style.font.caption
      wrapMode: Text.NoWrap
      elide: Text.ElideRight
    }

    Text {
      textFormat: Text.PlainText
      width: parent.width
      text: Logic.nodeMetadataLabel(root.node)
      color: root.palette.foreground
      font.family: root.palette.fontFamily
      font.pixelSize: Style.font.caption
      wrapMode: Text.NoWrap
      elide: Text.ElideRight
    }

    Text {
      textFormat: Text.PlainText
      width: parent.width
      text: {
        var lastSeen = Logic.compactAbsoluteLocalTime(root.node.lastSeenAt, root.nowMs)
        return lastSeen ? "Last seen " + lastSeen : "No observation timestamp"
      }
      Accessible.name: text
      Accessible.description: {
        var full = Logic.absoluteLocalTime(root.node.lastSeenAt)
        return full ? "Full local time " + full : ""
      }
      color: root.palette.selectedDim
      font.family: root.palette.fontFamily
      font.pixelSize: Style.font.caption
      wrapMode: Text.NoWrap
      elide: Text.ElideRight
    }

    Text {
      textFormat: Text.PlainText
      width: parent.width
      text: {
        var observed = Logic.compactAbsoluteLocalTime(root.observedAt, root.nowMs)
        return observed ? "Observed " + observed : ""
      }
      Accessible.name: text
      Accessible.description: {
        var full = Logic.absoluteLocalTime(root.observedAt)
        return full ? "Full local time " + full : ""
      }
      color: root.palette.selectedDim
      font.family: root.palette.fontFamily
      font.pixelSize: Style.font.caption
      wrapMode: Text.NoWrap
      elide: Text.ElideRight
    }
  }
}
