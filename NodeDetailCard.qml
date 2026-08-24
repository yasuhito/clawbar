import QtQuick
import qs.Commons
import "ClawbarLogic.js" as Logic

Item {
  id: root

  required property var node
  required property string observedAt
  required property bool historical
  required property double nowMs
  required property color foreground
  required property color dim
  required property string fontFamily

  implicitHeight: detailColumn.implicitHeight + Style.space(16)

  Column {
    id: detailColumn
    anchors.left: parent.left
    anchors.right: parent.right
    anchors.top: parent.top
    anchors.margins: Style.space(8)
    spacing: Style.space(4)

    Text {
      visible: root.historical
      width: parent.width
      text: "Last known · " + Logic.relativeTime(root.observedAt, root.nowMs)
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
    }

    Text {
      width: parent.width
      text: Logic.nodeMetadataLabel(root.node)
      color: root.foreground
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
      wrapMode: Text.Wrap
    }

    Text {
      width: parent.width
      text: {
        var lastSeen = Logic.absoluteLocalTime(root.node.lastSeenAt)
        return lastSeen ? "Last seen " + lastSeen : "No observation timestamp"
      }
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
      wrapMode: Text.Wrap
    }

    Text {
      width: parent.width
      text: {
        var observed = Logic.absoluteLocalTime(root.observedAt)
        return observed ? "Observed " + observed : ""
      }
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
      wrapMode: Text.Wrap
    }
  }
}
