import QtQuick
import qs.Commons
import qs.Ui
import "ClawbarLogic.js" as Logic

Item {
  id: root

  required property var automation
  required property double nowMs
  required property bool historical
  required property bool historyAvailable
  required property bool historyBusy
  required property color foreground
  required property color dim
  required property color accent
  required property string fontFamily

  signal historyRequested()

  implicitHeight: detailColumn.implicitHeight + Style.space(16)

  Column {
    id: detailColumn
    anchors.left: parent.left
    anchors.right: parent.right
    anchors.top: parent.top
    anchors.margins: Style.space(8)
    spacing: Style.space(8)

    Text {
      width: parent.width
      text: {
        var lines = []
        if (root.historical)
          lines.push("Last known · " + Logic.relativeTime(root.automation.lastRunAt, root.nowMs))
        lines.push(
          Logic.automationKindLabel(root.automation.kind)
            + " · " + Logic.automationStatusLabel(root.automation)
        )
        var nextRun = Logic.absoluteLocalTime(root.automation.nextRunAt)
        var lastRun = Logic.absoluteLocalTime(root.automation.lastRunAt)
        if (nextRun) lines.push("Next run " + nextRun)
        if (lastRun) lines.push("Last run " + lastRun)
        if (!nextRun && !lastRun && root.automation.lastResult === "none")
          lines.push("No run timestamps")
        if (!root.historyAvailable)
          lines.push("Run history unavailable for this Gateway Target")
        return lines.join("\n")
      }
      color: root.foreground
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
      wrapMode: Text.Wrap
    }

    Button {
      visible: root.historyAvailable
      width: parent.width
      text: root.historyBusy ? "Opening…" : "View run history"
      enabled: !root.historyBusy
      foreground: root.foreground
      accent: root.accent
      fontFamily: root.fontFamily
      fontSize: Style.font.caption
      bordered: true
      onClicked: root.historyRequested()
    }
  }
}
