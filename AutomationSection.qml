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
  required property color accent
  required property color urgent
  required property string fontFamily

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
          visible: !!root.section && !root.section.available
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
            width: root.width
            height: Style.space(48)
            radius: Style.cornerRadius
            color: selected ? Style.selectedFillFor(root.foreground, root.accent) : "transparent"
            border.width: selected ? 1 : 0
            border.color: root.accent

            MouseArea {
              anchors.fill: parent
              onClicked: root.rowSelected(automationRow.row)
            }

            Text {
              anchors.left: parent.left
              anchors.leftMargin: Style.space(9)
              anchors.verticalCenter: automationName.verticalCenter
              text: automationRow.modelData.enabled ? "●" : "◌"
              color: automationRow.failed
                ? root.urgent
                : automationRow.modelData.enabled ? root.accent : root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }

            Text {
              id: automationName
              anchors.left: parent.left
              anchors.leftMargin: Style.space(26)
              anchors.right: automationStatus.left
              anchors.rightMargin: Style.space(8)
              anchors.top: parent.top
              anchors.topMargin: Style.space(6)
              text: automationRow.modelData.name
              elide: Text.ElideRight
              color: automationRow.modelData.enabled ? root.foreground : root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.body
              font.bold: automationRow.modelData.enabled
            }

            Text {
              id: automationStatus
              anchors.right: parent.right
              anchors.rightMargin: Style.space(8)
              anchors.verticalCenter: automationName.verticalCenter
              text: Logic.automationStatusLabel(automationRow.modelData)
              color: automationRow.failed ? root.urgent : root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }

            Text {
              anchors.left: automationName.left
              anchors.right: parent.right
              anchors.rightMargin: Style.space(8)
              anchors.bottom: parent.bottom
              anchors.bottomMargin: Style.space(6)
              text: Logic.automationTimingLabel(automationRow.modelData, root.nowMs)
              elide: Text.ElideRight
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }
          }
        }
}
