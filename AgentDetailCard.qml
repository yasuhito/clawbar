import QtQuick
import qs.Commons
import "ClawbarLogic.js" as Logic

Item {
  id: root

  required property var agent
  required property string observedAt
  required property bool historical
  required property double nowMs
  required property color foreground
  required property color dim
  required property color urgent
  required property string fontFamily

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
      visible: root.historical
      width: parent.width
      text: "Last known · " + Logic.relativeTime(root.observedAt, root.nowMs)
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
    }

    Text {
      width: parent.width
      text: "Activity " + Logic.signalPresentation(root.agent.activity).label
      color: root.foreground
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
    }

    Text {
      width: parent.width
      text: {
        if (!root.taskResult || root.taskResult.state === "none") return "Task result None"
        return "Task result " + (root.taskResult.state === "succeeded" ? "Succeeded" : "Failed")
      }
      color: root.taskFailed ? root.urgent : root.foreground
      font.bold: root.taskFailed
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
    }

    Text {
      width: parent.width
      text: {
        var completed = Logic.absoluteLocalTime(root.taskResult.completedAt)
        return completed ? "Completed " + completed : "No completion timestamp"
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
