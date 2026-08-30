// Snapshot: the state machine over collected snapshots — freshness rules,
// section extraction, bar aggregation, and refresh request coalescing.
// Presentation turns sectionData() into view-models; Color adjusts contrast.

var DEFAULT_REFRESH_INTERVAL_SECONDS = 30
var MIN_REFRESH_INTERVAL_SECONDS = 15
var MAX_REFRESH_INTERVAL_SECONDS = 300
var SNAPSHOT_STALE_INTERVALS = 3

function normalizeRefreshInterval(rawValue) {
  var value = Number(rawValue)
  if (!isFinite(value) || Math.floor(value) !== value)
    return DEFAULT_REFRESH_INTERVAL_SECONDS
  if (value < MIN_REFRESH_INTERVAL_SECONDS || value > MAX_REFRESH_INTERVAL_SECONDS)
    return DEFAULT_REFRESH_INTERVAL_SECONDS
  return value
}

function snapshotState(snapshot, nowMilliseconds) {
  if (!snapshot || snapshot.schemaVersion !== 1 || !snapshot.gateway)
    throw new Error("Unsupported Clawbar snapshot")
  var state = String(snapshot.gateway.state || "unknown")
  var supportedStates = ["healthy", "degraded", "unstable", "offline", "configuration_error", "setup_required", "no_data", "unknown"]
  if (supportedStates.indexOf(state) === -1)
    throw new Error("Unsupported Gateway state")
  if (state === "setup_required" || state === "no_data" || state === "unknown") return state

  var generatedAt = Date.parse(String(snapshot.generatedAt || ""))
  var refreshInterval = normalizeRefreshInterval(snapshot.refreshIntervalSeconds)
  if (isNaN(generatedAt)) throw new Error("Invalid snapshot generation time")
  var staleAfter = refreshInterval * SNAPSHOT_STALE_INTERVALS * 1000
  return nowMilliseconds - generatedAt > staleAfter ? "stale" : state
}

function historicalState(state) {
  return state === "unstable" || state === "offline" || state === "stale"
}

function metadataSnapshot(snapshot, state) {
  if (!snapshot || !historicalState(state)) return snapshot
  return snapshot.lastKnown || snapshot
}

function observationTime(snapshot, state) {
  if (!snapshot || !historicalState(state)) return ""
  if (snapshot.lastKnown)
    return String(snapshot.lastKnown.observedAt || "")
  return String(snapshot.lastSuccessAt || snapshot.generatedAt || "")
}

function fleetNodes(snapshot, state) {
  var metadata = metadataSnapshot(snapshot, state)
  return metadata && metadata.fleet && metadata.fleet.available
    && Array.isArray(metadata.fleet.nodes) ? metadata.fleet.nodes : []
}

function agents(snapshot, state) {
  var metadata = metadataSnapshot(snapshot, state)
  return metadata && metadata.agents && metadata.agents.available
    && Array.isArray(metadata.agents.items) ? metadata.agents.items : []
}

function automations(snapshot, state) {
  var metadata = metadataSnapshot(snapshot, state)
  return metadata && metadata.automations && metadata.automations.available
    && Array.isArray(metadata.automations.items) ? metadata.automations.items : []
}

function setupCandidates(snapshot, state) {
  if (state !== "setup_required" && state !== "configuration_error") return []
  var setup = snapshot && snapshot.setup
  return setup && Array.isArray(setup.candidates) ? setup.candidates : []
}

// Everything the Operational Panel view-model needs, extracted in one call.
// Clawbar.qml owns the Snapshot boundary; lower QML receives only the resulting
// panel model.
function sectionData(snapshot, state) {
  var metadata = metadataSnapshot(snapshot, state)
  var setup = snapshot && snapshot.setup
  return {
    state: state,
    generatedAt: snapshot ? String(snapshot.generatedAt || "") : "",
    historical: historicalState(state),
    observedAt: observationTime(snapshot, state),
    setup: setup ? {
      present: true,
      guidance: String(setup.guidance || ""),
      error: String(setup.error || "")
    } : { present: false, guidance: "", error: "" },
    fleet: metadata && metadata.fleet ? {
      available: metadata.fleet.available === true,
      reason: String(metadata.fleet.reason || "")
    } : null,
    agentsSection: metadata && metadata.agents ? {
      available: metadata.agents.available === true,
      reason: String(metadata.agents.reason || "")
    } : null,
    automationsSection: metadata && metadata.automations ? {
      available: metadata.automations.available === true,
      reason: String(metadata.automations.reason || "")
    } : null,
    candidates: setupCandidates(snapshot, state),
    nodes: fleetNodes(snapshot, state),
    agents: agents(snapshot, state),
    automations: automations(snapshot, state)
  }
}

function barSeverity(snapshot, state) {
  if (state === "offline" || state === "configuration_error") return "critical"
  if (state !== "healthy" && state !== "degraded") return "warning"
  if (snapshot && snapshot.bar && snapshot.bar.severity === "critical") return "critical"
  return state === "degraded" ? "warning" : "healthy"
}

function barCount(snapshot, state) {
  if (state === "collecting" || state === "unknown" || state === "setup_required") return 0
  if (state === "stale" || state === "configuration_error") return 1
  var count = snapshot && snapshot.bar && snapshot.bar.kind === "attention"
    ? Number(snapshot.bar.count) : 0
  if (!isFinite(count) || count < 0) count = 0
  count = Math.floor(count)
  if (state === "no_data") return count
  if (barSeverity(snapshot, state) !== "healthy") return Math.max(1, count)
  return count
}

function requestRefresh(running) {
  return {
    start: !running,
    pending: running
  }
}

function consumeRefresh(running, pending) {
  return {
    wait: running,
    start: !running && pending,
    pending: running && pending
  }
}

if (typeof module !== "undefined") {
  module.exports = {
    normalizeRefreshInterval: normalizeRefreshInterval,
    snapshotState: snapshotState,
    historicalState: historicalState,
    metadataSnapshot: metadataSnapshot,
    observationTime: observationTime,
    fleetNodes: fleetNodes,
    agents: agents,
    automations: automations,
    setupCandidates: setupCandidates,
    sectionData: sectionData,
    barSeverity: barSeverity,
    barCount: barCount,
    requestRefresh: requestRefresh,
    consumeRefresh: consumeRefresh
  }
}
