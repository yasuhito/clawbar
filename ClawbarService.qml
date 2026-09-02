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
  property string collectorPath: decodeURIComponent(String(Qt.resolvedUrl("scripts/clawbar_collect.py")).replace(/^file:\/\//, ""))
  property int refreshIntervalSeconds: Snapshot.normalizeRefreshInterval(Quickshell.env("CLAWBAR_REFRESH_INTERVAL_SECONDS"))
  readonly property bool processRunning: collector.running || candidateVerifier.running
  readonly property bool collecting: processRunning || processSettling || refreshPending || candidatePending !== ""
  readonly property bool interactiveRefreshing: (collector.running && collectorInteractive) || refreshPendingInteractive
  readonly property bool verifyingCandidate: candidateVerifier.running || candidatePending !== ""

  signal collectionFinished(bool interactive, bool succeeded)

  function busy() {
    return processRunning || processSettling;
  }

  function startCollection(interactive) {
    collectorInteractive = !!interactive;
    collector.command = ["python3", root.collectorPath, "--refresh-interval", String(root.refreshIntervalSeconds), "--status-only"];
    collector.running = true;
  }

  function requestCollection(interactive) {
    if (busy()) {
      refreshPending = true;
      refreshPendingInteractive = refreshPendingInteractive || !!interactive;
      return;
    }
    startCollection(interactive);
  }

  function verifyCandidate(candidateKey) {
    if (!candidateKey)
      return;
    if (busy()) {
      candidatePending = candidateKey;
      return;
    }
    candidateVerifier.command = ["python3", root.collectorPath, "--refresh-interval", String(root.refreshIntervalSeconds), "--verify-candidate", candidateKey, "--status-only"];
    candidateVerifier.running = true;
  }

  function processSucceeded(raw) {
    try {
      return JSON.parse(raw).succeeded === true;
    } catch (_) {
      return false;
    }
  }

  function finishProcess(raw, interactive) {
    processSettling = true;
    var succeeded = processSucceeded(raw);
    Qt.callLater(function () {
      root.consumeCollection(interactive, succeeded);
    });
  }

  function consumeCollection(interactive, succeeded) {
    if (processRunning) {
      Qt.callLater(function () {
        root.consumeCollection(interactive, succeeded);
      });
      return;
    }
    processSettling = false;
    collectionFinished(interactive, succeeded);
    if (candidatePending) {
      var candidateKey = candidatePending;
      candidatePending = "";
      verifyCandidate(candidateKey);
    } else if (refreshPending) {
      var pendingInteractive = refreshPendingInteractive;
      refreshPending = false;
      refreshPendingInteractive = false;
      root.startCollection(pendingInteractive);
    }
  }

  Process {
    id: collector
    stdout: StdioCollector {
      onStreamFinished: {
        var interactive = root.collectorInteractive;
        root.collectorInteractive = false;
        root.finishProcess(text, interactive);
      }
    }
  }

  Process {
    id: candidateVerifier
    stdout: StdioCollector {
      onStreamFinished: root.finishProcess(text, false)
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
