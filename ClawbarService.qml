import QtQuick
import Quickshell
import Quickshell.Io
import "ClawbarSnapshot.js" as Snapshot

Item {
  id: root
  visible: false

  property bool refreshPending: false
  property bool refreshPendingInteractive: false
  property bool collectorInteractive: false
  property bool processSettling: false
  property string candidatePending: ""
  property string collectorPath: decodeURIComponent(
    String(Qt.resolvedUrl("scripts/clawbar_collect.py")).replace(/^file:\/\//, "")
  )
  property int refreshIntervalSeconds: Snapshot.normalizeRefreshInterval(
    Quickshell.env("CLAWBAR_REFRESH_INTERVAL_SECONDS")
  )
  readonly property bool processRunning: collector.running || candidateVerifier.running
  readonly property bool collecting: processRunning || processSettling
    || refreshPending || candidatePending !== ""
  readonly property bool interactiveRefreshing: (collector.running && collectorInteractive)
    || refreshPendingInteractive
  readonly property bool verifyingCandidate: candidateVerifier.running || candidatePending !== ""

  signal collectionFinished(bool interactive, bool succeeded)

  function busy() {
    return processRunning || processSettling
  }

  function startCollection(interactive) {
    collectorInteractive = !!interactive
    collector.running = true
  }

  function requestCollection(interactive) {
    if (busy()) {
      refreshPending = true
      refreshPendingInteractive = refreshPendingInteractive || !!interactive
      return
    }
    startCollection(interactive)
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

  function consumeCollection(interactive, succeeded) {
    if (processRunning) {
      Qt.callLater(function() { root.consumeCollection(interactive, succeeded) })
      return
    }
    processSettling = false
    collectionFinished(interactive, succeeded)
    if (candidatePending) {
      var candidateKey = candidatePending
      candidatePending = ""
      verifyCandidate(candidateKey)
    } else if (refreshPending) {
      var pendingInteractive = refreshPendingInteractive
      refreshPending = false
      refreshPendingInteractive = false
      root.startCollection(pendingInteractive)
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
    onExited: function(exitCode) {
      var interactive = root.collectorInteractive
      root.collectorInteractive = false
      root.processSettling = true
      Qt.callLater(function() { root.consumeCollection(interactive, exitCode === 0) })
    }
  }

  Process {
    id: candidateVerifier
    onExited: function(exitCode) {
      root.processSettling = true
      Qt.callLater(function() { root.consumeCollection(false, exitCode === 0) })
    }
  }

  Timer {
    interval: root.refreshIntervalSeconds * 1000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.requestCollection(false)
  }
}
