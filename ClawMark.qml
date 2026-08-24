import QtQuick
import QtQuick.Shapes

Item {
  id: root

  property color color: "white"
  property bool animated: false
  property real flexAngle: 0
  property real jawAngle: -10

  implicitWidth: 24
  implicitHeight: 24

  /*
   * MOTION STORYBOARD
   *
   * Source of truth: OpenClaw v2026.8.1-beta.3
   *   ui/src/components/icons-tools.ts          (toolIcons.claw)
   *   ui/src/styles/components.css              (shared claw keyframes)
   *   ui/src/styles/chat/tool-cards.css         (18px working indicator)
   *
   * The lower body and upper jaw below copy OpenClaw's two 24x24 paths
   * verbatim. The jaw uses the same (8.6, 11) hinge and -10deg resting pose.
   * The 2.4s flex/snip keyframes are translated directly from CSS percentages
   * into millisecond segments; no inferred connector geometry is added.
   */
  Item {
    id: motionFrame
    anchors.centerIn: parent
    width: 24
    height: 24
    scale: Math.min(root.width, root.height) / 24 * 0.9
    rotation: root.flexAngle

    Shape {
      anchors.fill: parent
      preferredRendererType: Shape.CurveRenderer

      ShapePath {
        fillColor: root.color
        strokeColor: "transparent"

        PathSvg {
          path: "M8.2 10 A5.2 5.2 0 1 0 8.2 20.4 A5.2 5.2 0 0 0 8.2 10 Z"
        }
      }

      ShapePath {
        fillColor: root.color
        strokeColor: "transparent"

        PathSvg {
          path: "M10.2 20 C14.5 20.8 19 18.6 22.3 13.2 C21 12.9 19.7 12.7 18.4 12.8 L17.5 14.6 L16 12.9 L14.3 14.5 L13.5 13 L11.5 14.2 Z"
        }
      }
    }

    Shape {
      anchors.fill: parent
      preferredRendererType: Shape.CurveRenderer
      transform: Rotation {
        origin.x: 8.6
        origin.y: 11
        angle: root.jawAngle
      }

      ShapePath {
        fillColor: root.color
        strokeColor: "transparent"

        PathSvg {
          path: "M5.6 12.2 C5.2 5.6 10.4 1.4 15.6 2 C19.4 2.6 21.8 5.2 22.6 8.2 C20.9 7.7 19.2 7.6 17.6 7.9 L16.9 6.3 L15.2 8.5 C13.6 9.4 12.2 10.9 11.6 12.4 L6.8 13 Z"
        }
      }
    }
  }

  SequentialAnimation {
    running: root.animated
    loops: Animation.Infinite

    PauseAnimation { duration: 144 }
    NumberAnimation { target: root; property: "flexAngle"; to: -4; duration: 96; easing.type: Easing.OutCubic }
    NumberAnimation { target: root; property: "flexAngle"; to: 3; duration: 144; easing.type: Easing.OutCubic }
    NumberAnimation { target: root; property: "flexAngle"; to: -4; duration: 144; easing.type: Easing.OutCubic }
    PauseAnimation { duration: 96 }
    NumberAnimation { target: root; property: "flexAngle"; to: 3; duration: 144; easing.type: Easing.OutCubic }
    NumberAnimation { target: root; property: "flexAngle"; to: 0; duration: 240; easing.type: Easing.OutCubic }
    PauseAnimation { duration: 1392 }

    onStopped: root.flexAngle = 0
  }

  SequentialAnimation {
    running: root.animated
    loops: Animation.Infinite

    PauseAnimation { duration: 144 }
    NumberAnimation { target: root; property: "jawAngle"; to: -26; duration: 96; easing.type: Easing.OutCubic }
    NumberAnimation { target: root; property: "jawAngle"; to: 4; duration: 144; easing.type: Easing.OutCubic }
    NumberAnimation { target: root; property: "jawAngle"; to: -24; duration: 144; easing.type: Easing.OutCubic }
    PauseAnimation { duration: 96 }
    NumberAnimation { target: root; property: "jawAngle"; to: 4; duration: 144; easing.type: Easing.OutCubic }
    NumberAnimation { target: root; property: "jawAngle"; to: -10; duration: 240; easing.type: Easing.OutCubic }
    PauseAnimation { duration: 1392 }

    onStopped: root.jawAngle = -10
  }
}
