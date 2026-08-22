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
    sourceComponent: root.kind === "triangle" ? triangle
      : root.kind === "diamond" ? diamond
      : root.kind === "dotted" ? dotted
      : circle
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
    id: diamond

    Rectangle {
      width: Math.min(root.width, root.height) * 0.7
      height: width
      rotation: 45
      color: root.color
    }
  }

  Component {
    id: triangle

    Shape {
      width: 10
      height: 10
      scale: Math.min(root.width, root.height) / 10
      preferredRendererType: Shape.CurveRenderer

      ShapePath {
        fillColor: root.color
        strokeColor: "transparent"

        PathSvg { path: "M5 0L10 9H0Z" }
      }
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
