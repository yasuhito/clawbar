import QtQuick
import qs.Commons
import "ClawbarLogic.js" as Logic

Column {
  id: root

  required property var section
  required property var automations
  required property var rows
  required property int rowOffset
  required property string selectedKey
  required property double nowMs
  required property color foreground
  required property color dim
  required property color selectedDim
  required property color accent
  required property color urgent
  required property string fontFamily
  required property bool historical
  required property bool showUnavailable
  required property var signalColor
  required property var selectedSignalColor

  signal rowSelected(var row)

  spacing: Style.space(4)

  function itemAt(index) {
    return automationRepeater.itemAt(index)
  }

  Text {
    width: parent.width
    topPadding: Style.space(8)
    text: "AUTOMATIONS"
    color: root.dim
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
    font.bold: true
  }

  Text {
    visible: root.showUnavailable && !!root.section && !root.section.available
    width: parent.width
    text: root.section && root.section.reason === "more_than_500"
      ? "Unavailable — more than 500 Automations"
      : "Unavailable"
    color: root.dim
    font.family: root.fontFamily
    font.pixelSize: Style.font.body
  }

  Text {
    visible: !!root.section && root.section.available && root.automations.length === 0
    width: parent.width
    text: "No Automations"
    color: root.dim
    font.family: root.fontFamily
    font.pixelSize: Style.font.body
  }

  Repeater {
    id: automationRepeater
    model: root.automations

    delegate: Rectangle {
      id: automationRow
      required property var modelData
      required property int index
      readonly property var row: root.rows[root.rowOffset + index]
      readonly property bool selected: !!row && root.selectedKey === row.key
      readonly property bool failed: modelData.enabled && modelData.lastResult === "error"
      readonly property string signalState: failed ? "failed"
        : !modelData.enabled ? "disabled"
        : modelData.lastResult === "ok" ? "succeeded" : "healthy"
      readonly property var signal: Logic.signalPresentation(signalState)
      readonly property bool showStatus: Logic.showAutomationStatusLabel(modelData, root.historical)
      width: root.width
      height: automationSummary.height + (selected ? automationDetail.implicitHeight : 0)
      radius: Style.cornerRadius
      opacity: root.historical && !selected ? 0.55 : 1
      color: selected ? Style.selectedFillFor(root.foreground, root.accent) : "transparent"
      border.width: selected ? 1 : 0
      border.color: root.accent
      Accessible.name: modelData.name
      Accessible.description: root.historical ? "Last known" : Logic.automationStatusLabel(modelData)

      Item {
        id: automationSummary
        width: parent.width
        height: Style.space(48)

        MouseArea {
          anchors.fill: parent
          onClicked: root.rowSelected(automationRow.row)
        }

        SignalPoint {
          anchors.left: parent.left
          anchors.leftMargin: Style.space(8)
          anchors.verticalCenter: automationName.verticalCenter
          kind: automationRow.signal.shape
          color: automationRow.selected ? root.selectedSignalColor(automationRow.signal.tone)
            : root.signalColor(automationRow.signal.tone)
        }

        Text {
          id: automationName
          anchors.left: parent.left
          anchors.leftMargin: Style.space(26)
          anchors.right: automationRow.showStatus ? automationStatus.left : parent.right
          anchors.rightMargin: Style.space(8)
          anchors.top: parent.top
          anchors.topMargin: Style.space(6)
          text: automationRow.modelData.name
          elide: Text.ElideRight
          color: automationRow.modelData.enabled ? root.foreground
            : automationRow.selected ? root.selectedDim : root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
          font.bold: automationRow.modelData.enabled
        }

        Text {
          id: automationStatus
          visible: automationRow.showStatus
          anchors.right: parent.right
          anchors.rightMargin: Style.space(8)
          anchors.verticalCenter: automationName.verticalCenter
          width: Math.min(implicitWidth, parent.width * 0.42)
          text: root.historical ? "Last known" : Logic.automationCompactStatusLabel(automationRow.modelData)
          color: automationRow.selected ? root.selectedSignalColor(automationRow.signal.tone)
            : root.historical ? root.dim : root.signalColor(automationRow.signal.tone)
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          elide: Text.ElideRight
          horizontalAlignment: Text.AlignRight
        }

        Text {
          anchors.left: automationName.left
          anchors.right: parent.right
          anchors.rightMargin: Style.space(8)
          anchors.bottom: parent.bottom
          anchors.bottomMargin: Style.space(6)
          text: {
            if (!root.historical)
              return Logic.automationTimingLabel(automationRow.modelData, root.nowMs)
            var last = Logic.relativeTime(automationRow.modelData.lastRunAt, root.nowMs)
            return last ? "Last " + last : "No runs yet"
          }
          elide: Text.ElideRight
          color: automationRow.selected ? root.selectedDim : root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
        }
      }

      AutomationDetailCard {
        id: automationDetail
        visible: automationRow.selected
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: automationSummary.bottom
        height: implicitHeight
        automation: automationRow.modelData
        nowMs: root.nowMs
        historical: root.historical
        foreground: root.foreground
        dim: root.selectedDim
        fontFamily: root.fontFamily
      }
    }
  }
}
