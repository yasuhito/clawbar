import QtQuick
import qs.Commons
import qs.Ui

// Fixed panel header: claw mark, product title, Gateway signal and the
// summary / observation-time captions. Purely presentational.
Item {
  id: root

  required property var palette
  required property var gatewaySignal
  required property string summary
  required property string timeCaption

  anchors.left: parent.left
  anchors.right: parent.right
  anchors.top: parent.top
  height: Style.space(60)

  ClawMark {
    id: panelClaw
    anchors.left: parent.left
    anchors.top: parent.top
    width: Style.space(20)
    height: width
    color: root.palette.foreground
  }

  Text {
    textFormat: Text.PlainText
    anchors.left: panelClaw.right
    anchors.leftMargin: Style.space(8)
    anchors.top: parent.top
    anchors.right: gatewayStatus.left
    anchors.rightMargin: Style.space(8)
    text: "OpenClaw"
    elide: Text.ElideRight
    color: root.palette.foreground
    font.family: root.palette.fontFamily
    font.pixelSize: Style.font.title
    font.bold: true
  }

  Row {
    id: gatewayStatus
    anchors.right: parent.right
    anchors.top: parent.top
    spacing: Style.space(5)

    SignalPoint {
      anchors.verticalCenter: parent.verticalCenter
      kind: root.gatewaySignal.shape
      color: root.palette.signalColor(root.gatewaySignal.tone)
    }

    Text {
      textFormat: Text.PlainText
      text: root.gatewaySignal.label
      color: root.palette.signalColor(root.gatewaySignal.tone)
      font.family: root.palette.fontFamily
      font.pixelSize: Style.font.caption
      font.bold: true
    }
  }

  Text {
    textFormat: Text.PlainText
    anchors.left: parent.left
    anchors.right: observedTime.left
    anchors.rightMargin: Style.space(8)
    anchors.bottom: headerDivider.top
    anchors.bottomMargin: Style.space(4)
    text: root.summary
    elide: Text.ElideRight
    color: root.palette.dim
    font.family: root.palette.fontFamily
    font.pixelSize: Style.font.caption
  }

  Text {
    id: observedTime
    textFormat: Text.PlainText
    anchors.right: parent.right
    anchors.bottom: headerDivider.top
    anchors.bottomMargin: Style.space(4)
    text: root.timeCaption
    color: root.palette.dim
    font.family: root.palette.fontFamily
    font.pixelSize: Style.font.caption
  }

  Rectangle {
    id: headerDivider
    anchors.left: parent.left
    anchors.right: parent.right
    anchors.bottom: parent.bottom
    height: 1
    color: root.palette.dim
    opacity: 0.28
  }
}
