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
  var supportedStates = ["healthy", "unstable", "offline", "configuration_error", "unknown"]
  if (supportedStates.indexOf(state) === -1)
    throw new Error("Unsupported Gateway state")
  if (state !== "healthy") return state

  var generatedAt = Date.parse(String(snapshot.generatedAt || ""))
  var refreshInterval = normalizeRefreshInterval(snapshot.refreshIntervalSeconds)
  if (isNaN(generatedAt)) throw new Error("Invalid snapshot generation time")
  var staleAfter = refreshInterval * SNAPSHOT_STALE_INTERVALS * 1000
  return nowMilliseconds - generatedAt > staleAfter ? "stale" : "healthy"
}

function summary(state, resolutionSource) {
  if (state === "healthy") {
    if (resolutionSource === "node_host") return "Node-host OpenClaw Gateway healthy"
    if (resolutionSource === "configured_remote") return "Remote OpenClaw Gateway healthy"
    return "Local OpenClaw Gateway healthy"
  }
  if (state === "unstable") return "OpenClaw Gateway unstable"
  if (state === "offline") return "OpenClaw Gateway offline"
  if (state === "configuration_error") return "OpenClaw Gateway configuration error"
  if (state === "stale") return "OpenClaw Gateway snapshot stale"
  return "OpenClaw Gateway status unavailable"
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
    summary: summary,
    requestRefresh: requestRefresh,
    consumeRefresh: consumeRefresh
  }
}
