import QtQuick

// Owns the shared detail-reveal storyboard: surface updates immediately,
// content fades over 120 ms while height settles over 180 ms.
// Hosts one detail card; callers provide expanded + contentHeight.
Item {
  id: root

  required property bool expanded
  required property real contentHeight
  property bool motionEnabled: true
  property int fadeDuration: 120
  property int expandDuration: 180

  visible: expanded || height > 0
  height: expanded ? contentHeight : 0
  opacity: expanded ? 1 : 0
  clip: true
  Accessible.ignored: !expanded

  Behavior on height {
    enabled: root.motionEnabled
    NumberAnimation {
      duration: root.expandDuration
      easing.type: Easing.OutCubic
    }
  }

  Behavior on opacity {
    enabled: root.motionEnabled
    NumberAnimation {
      duration: root.fadeDuration
      easing.type: Easing.OutCubic
    }
  }
}
