import QtQuick
import qs.Commons
import "ClawbarLogic.js" as Logic

Item {
  id: root

  required property var automation
  required property double nowMs
  required property bool historical
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
      textFormat: Text.PlainText
      visible: root.historical
      width: parent.width
      text: "Last known · " + Logic.relativeTime(root.automation.lastRunAt, root.nowMs)
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
      wrapMode: Text.NoWrap
      elide: Text.ElideRight
    }

    Text {
      textFormat: Text.PlainText
      width: parent.width
      text: Logic.automationKindLabel(root.automation.kind)
        + " · " + Logic.automationStatusLabel(root.automation)
      color: root.foreground
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
      wrapMode: Text.NoWrap
      elide: Text.ElideRight
    }

    Text {
      textFormat: Text.PlainText
      visible: !!Logic.compactAbsoluteLocalTime(root.automation.nextRunAt, root.nowMs)
      width: parent.width
      text: "Next run " + Logic.compactAbsoluteLocalTime(root.automation.nextRunAt, root.nowMs)
      Accessible.name: text
      Accessible.description: {
        var full = Logic.absoluteLocalTime(root.automation.nextRunAt)
        return full ? "Full local time " + full : ""
      }
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
      wrapMode: Text.NoWrap
      elide: Text.ElideRight
    }

    Text {
      textFormat: Text.PlainText
      visible: !!Logic.compactAbsoluteLocalTime(root.automation.lastRunAt, root.nowMs)
      width: parent.width
      text: "Last run " + Logic.compactAbsoluteLocalTime(root.automation.lastRunAt, root.nowMs)
      Accessible.name: text
      Accessible.description: {
        var full = Logic.absoluteLocalTime(root.automation.lastRunAt)
        return full ? "Full local time " + full : ""
      }
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
      wrapMode: Text.NoWrap
      elide: Text.ElideRight
    }

    Text {
      textFormat: Text.PlainText
      visible: !Logic.compactAbsoluteLocalTime(root.automation.nextRunAt, root.nowMs)
        && !Logic.compactAbsoluteLocalTime(root.automation.lastRunAt, root.nowMs)
        && root.automation.lastResult === "none"
      width: parent.width
      text: "No run timestamps"
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
      wrapMode: Text.NoWrap
      elide: Text.ElideRight
    }
  }
}
