import QtQuick
import QtQuick.Shapes

Item {
  id: root

  property color color: "white"

  implicitWidth: 12
  implicitHeight: 12

  Shape {
    anchors.centerIn: parent
    width: 12
    height: 12
    scale: Math.min(root.width, root.height) / 12 * 0.86
    transform: Rotation {
      origin.x: 6
      origin.y: 6
      angle: -60
    }
    preferredRendererType: Shape.CurveRenderer

    ShapePath {
      fillColor: root.color
      strokeColor: "transparent"

      PathSvg {
        path: "M5.6 11C3 11 1.3 9.3 1.5 6.9C1.7 4.9 2.8 3.4 4.5 2.4C4.5 4 4.8 4.9 5.7 5.5C6.8 4.3 7.4 2.5 7.9.7C10.2 2 11.2 4.6 10.6 7.2C10 9.6 8 11 5.6 11Z"
      }
    }
  }
}
