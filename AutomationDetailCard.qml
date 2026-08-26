import QtQuick
import qs.Commons
import "ClawbarPresentation.js" as Presentation

Item {
  id: root

  // Uniform Operational Row detail interface: injected by RowSection's loader.
  required property var vm
  required property var palette
  required property double nowMs
  required property bool historical

  readonly property var automation: vm.item

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
      text: "Last known · " + Presentation.relativeTime(root.automation.lastRunAt, root.nowMs)
      color: root.palette.selectedDim
      font.family: root.palette.fontFamily
      font.pixelSize: Style.font.caption
      wrapMode: Text.NoWrap
      elide: Text.ElideRight
    }

    Text {
      textFormat: Text.PlainText
      width: parent.width
      text: Presentation.automationKindLabel(root.automation.kind)
        + " · " + Presentation.automationStatusLabel(root.automation)
      color: root.palette.foreground
      font.family: root.palette.fontFamily
      font.pixelSize: Style.font.caption
      wrapMode: Text.NoWrap
      elide: Text.ElideRight
    }

    Text {
      textFormat: Text.PlainText
      visible: !!Presentation.compactAbsoluteLocalTime(root.automation.nextRunAt, root.nowMs)
      width: parent.width
      text: "Next run " + Presentation.compactAbsoluteLocalTime(root.automation.nextRunAt, root.nowMs)
      Accessible.name: text
      Accessible.description: {
        var full = Presentation.absoluteLocalTime(root.automation.nextRunAt)
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
      visible: !!Presentation.compactAbsoluteLocalTime(root.automation.lastRunAt, root.nowMs)
      width: parent.width
      text: "Last run " + Presentation.compactAbsoluteLocalTime(root.automation.lastRunAt, root.nowMs)
      Accessible.name: text
      Accessible.description: {
        var full = Presentation.absoluteLocalTime(root.automation.lastRunAt)
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
      visible: !Presentation.compactAbsoluteLocalTime(root.automation.nextRunAt, root.nowMs)
        && !Presentation.compactAbsoluteLocalTime(root.automation.lastRunAt, root.nowMs)
        && root.automation.lastResult === "none"
      width: parent.width
      text: "No run timestamps"
      color: root.palette.selectedDim
      font.family: root.palette.fontFamily
      font.pixelSize: Style.font.caption
      wrapMode: Text.NoWrap
      elide: Text.ElideRight
    }
  }
}
