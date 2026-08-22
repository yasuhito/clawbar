import QtQuick
import Quickshell
import Quickshell.Io
import "ClawbarLogic.js" as Logic

Item {
  id: root
  visible: false

  property bool refreshPending: false
  property string collectorPath: decodeURIComponent(
    String(Qt.resolvedUrl("scripts/clawbar_collect.py")).replace(/^file:\/\//, "")
  )
  property int refreshIntervalSeconds: Logic.normalizeRefreshInterval(
    Quickshell.env("CLAWBAR_REFRESH_INTERVAL_SECONDS")
  )

  signal collectionFinished()

  function requestCollection() {
    var action = Logic.requestRefresh(collector.running)
    refreshPending = action.pending
    if (action.start) collector.running = true
  }

  function consumeCollection() {
    var action = Logic.consumeRefresh(collector.running, refreshPending)
    refreshPending = action.pending
    if (action.wait) {
      Qt.callLater(root.consumeCollection)
      return
    }
    collectionFinished()
    if (action.start) collector.running = true
  }

  Process {
    id: collector
    command: [
      "python3",
      root.collectorPath,
      "--refresh-interval",
      String(root.refreshIntervalSeconds)
    ]
    onExited: function(_) {
      Qt.callLater(root.consumeCollection)
    }
  }

  Timer {
    interval: root.refreshIntervalSeconds * 1000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.requestCollection()
  }
}
