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

  readonly property var agent: vm.item
  readonly property string observedAt: vm.observedAt
  readonly property color urgent: palette.selectedSignalColor("critical")

  readonly property var taskResult: agent.taskResult || ({})
  readonly property bool taskFailed: taskResult.state === "failed"

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
      text: "Last known · " + Presentation.relativeTime(root.observedAt, root.nowMs)
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
        if (!root.taskResult || root.taskResult.state === "none") return "Task result None"
        return "Task result " + (root.taskResult.state === "succeeded" ? "Succeeded" : "Failed")
      }
      color: root.taskFailed ? root.urgent : root.palette.foreground
      font.bold: root.taskFailed
      font.family: root.palette.fontFamily
      font.pixelSize: Style.font.caption
      wrapMode: Text.NoWrap
      elide: Text.ElideRight
    }

    Text {
      textFormat: Text.PlainText
      width: parent.width
      text: {
        var completed = Presentation.compactAbsoluteLocalTime(root.taskResult.completedAt, root.nowMs)
        return completed ? "Completed " + completed : "No completion timestamp"
      }
      Accessible.name: text
      Accessible.description: {
        var full = Presentation.absoluteLocalTime(root.taskResult.completedAt)
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
        var observed = Presentation.compactAbsoluteLocalTime(root.observedAt, root.nowMs)
        return observed ? "Observed " + observed : ""
      }
      Accessible.name: text
      Accessible.description: {
        var full = Presentation.absoluteLocalTime(root.observedAt)
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
