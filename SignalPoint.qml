import QtQuick
import QtQuick.Shapes

Item {
  id: root

  property string kind: "none"
  property color color: "transparent"

  implicitWidth: 10
  implicitHeight: 10
  visible: kind !== "none"

  Loader {
    anchors.centerIn: parent
    sourceComponent: root.kind === "dotted" ? dotted
      : root.kind === "ring" ? ring : circle
  }

  Component {
    id: circle

    Rectangle {
      width: Math.min(root.width, root.height) * 0.8
      height: width
      radius: width / 2
      color: root.color
    }
  }

  Component {
    id: ring

    Rectangle {
      width: Math.min(root.width, root.height) * 0.8
      height: width
      radius: width / 2
      color: "transparent"
      border.width: 1
      border.color: root.color
    }
  }

  Component {
    id: dotted

    Shape {
      width: 10
      height: 10
      scale: Math.min(root.width, root.height) / 10
      preferredRendererType: Shape.CurveRenderer

      ShapePath {
        fillColor: "transparent"
        strokeColor: root.color
        strokeWidth: 1
        strokeStyle: ShapePath.DashLine
        dashPattern: [1, 1]
        capStyle: ShapePath.RoundCap

        PathAngleArc {
          centerX: 5
          centerY: 5
          radiusX: 4
          radiusY: 4
          startAngle: 0
          sweepAngle: 360
        }
      }
    }
  }
}
