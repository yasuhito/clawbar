import QtQuick
import Quickshell
import Quickshell.Io
import "ClawbarLogic.js" as Logic

Item {
  id: root
  visible: false

  property bool refreshPending: false
  property string candidatePending: ""
  property string collectorPath: decodeURIComponent(
    String(Qt.resolvedUrl("scripts/clawbar_collect.py")).replace(/^file:\/\//, "")
  )
  property int refreshIntervalSeconds: Logic.normalizeRefreshInterval(
    Quickshell.env("CLAWBAR_REFRESH_INTERVAL_SECONDS")
  )
  readonly property bool verifyingCandidate: candidateVerifier.running || candidatePending !== ""

  signal collectionFinished()

  function busy() {
    return collector.running || candidateVerifier.running
  }

  function requestCollection() {
    if (busy()) {
      refreshPending = true
      return
    }
    collector.running = true
  }

  function verifyCandidate(candidateKey) {
    if (!candidateKey) return
    if (busy()) {
      candidatePending = candidateKey
      return
    }
    candidateVerifier.command = [
      "python3",
      root.collectorPath,
      "--refresh-interval",
      String(root.refreshIntervalSeconds),
      "--verify-candidate",
      candidateKey
    ]
    candidateVerifier.running = true
  }

  function consumeCollection() {
    if (busy()) {
      Qt.callLater(root.consumeCollection)
      return
    }
    collectionFinished()
    if (candidatePending) {
      var candidateKey = candidatePending
      candidatePending = ""
      verifyCandidate(candidateKey)
    } else if (refreshPending) {
      refreshPending = false
      collector.running = true
    }
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

  Process {
    id: candidateVerifier
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
