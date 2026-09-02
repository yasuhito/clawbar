import QtQuick
import qs.Commons
import "ClawbarPresentation.js" as Presentation

// Renders the bounded detail owned by any Operational Row view-model.
Item {
  id: root

  required property var vm
  required property var palette
  required property double nowMs

  implicitHeight: detailColumn.implicitHeight + Style.space(16)

  Column {
    id: detailColumn
    anchors.left: parent.left
    anchors.right: parent.right
    anchors.top: parent.top
    anchors.margins: Style.space(8)
    spacing: Style.space(4)

    Repeater {
      model: root.vm.detail

      delegate: Text {
        required property var modelData
        width: detailColumn.width
        textFormat: Text.PlainText
        text: Presentation.detailText(modelData, root.nowMs)
        Accessible.name: text
        Accessible.description: modelData.spoken
        color: modelData.critical ? root.palette.selectedSignalColor("critical") : modelData.label === "" || modelData.label === "Task result" ? root.palette.foreground : root.palette.selectedDim
        font.bold: modelData.critical
        font.family: root.palette.fontFamily
        font.pixelSize: Style.font.caption
        wrapMode: Text.NoWrap
        elide: Text.ElideRight
      }
    }
  }
}
