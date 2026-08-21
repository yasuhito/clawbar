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
  var supportedStates = ["healthy", "degraded", "unstable", "offline", "configuration_error", "unknown"]
  if (supportedStates.indexOf(state) === -1)
    throw new Error("Unsupported Gateway state")
  if (state !== "healthy" && state !== "degraded") return state

  var generatedAt = Date.parse(String(snapshot.generatedAt || ""))
  var refreshInterval = normalizeRefreshInterval(snapshot.refreshIntervalSeconds)
  if (isNaN(generatedAt)) throw new Error("Invalid snapshot generation time")
  var staleAfter = refreshInterval * SNAPSHOT_STALE_INTERVALS * 1000
  return nowMilliseconds - generatedAt > staleAfter ? "stale" : state
}

function fleetNodes(snapshot) {
  return snapshot && snapshot.fleet && snapshot.fleet.available
    && Array.isArray(snapshot.fleet.nodes) ? snapshot.fleet.nodes : []
}

function agents(snapshot) {
  return snapshot && snapshot.agents && snapshot.agents.available
    && Array.isArray(snapshot.agents.items) ? snapshot.agents.items : []
}

function nodeRow(item, index) {
  return {
    kind: "node",
    key: String(item.key || "node-index:" + index),
    sectionIndex: index,
    item: item,
    expandable: true,
    typeLabel: "Node",
    timestamp: item.lastSeenAt || "",
    missingTimestampLabel: "No observation timestamp"
  }
}

function agentRow(item, index) {
  var result = item.taskResult || {}
  return {
    kind: "agent",
    key: String(item.key || "agent:" + item.name),
    sectionIndex: index,
    item: item,
    expandable: false,
    typeLabel: "Agent",
    timestamp: result.completedAt || "",
    missingTimestampLabel: "No completion timestamp"
  }
}

function panelRows(snapshot) {
  return fleetNodes(snapshot).map(nodeRow).concat(agents(snapshot).map(agentRow))
}

function indexForKey(rows, key) {
  for (var i = 0; i < rows.length; i++)
    if (rows[i].key === key) return i
  return -1
}

function reconcileSelection(rows, selectedKey, indexHint) {
  if (rows.length === 0) return { key: "", index: -1 }
  var retained = indexForKey(rows, selectedKey)
  var index = retained >= 0 ? retained : Math.max(0, Math.min(indexHint, rows.length - 1))
  return { key: rows[index].key, index: index }
}

function reconcileExpanded(rows, expandedKeys) {
  var retained = {}
  for (var i = 0; i < rows.length; i++)
    if (rows[i].expandable && expandedKeys[rows[i].key]) retained[rows[i].key] = true
  return retained
}

function moveFocus(index, count, delta) {
  if (count <= 0) return -1
  var current = index >= 0 && index < count ? index : 0
  return ((current + delta) % count + count) % count
}

function workingCount(snapshot) {
  return agents(snapshot).filter(function(agent) { return agent.activity === "working" }).length
}

function relativeTime(value, nowMilliseconds) {
  var timestamp = Date.parse(String(value || ""))
  if (isNaN(timestamp)) return ""
  var seconds = Math.max(0, Math.floor((nowMilliseconds - timestamp) / 1000))
  if (seconds < 60) return "now"
  var minutes = Math.floor(seconds / 60)
  if (minutes < 60) return minutes + "m"
  var hours = Math.floor(minutes / 60)
  if (hours < 24) return hours + "h"
  return Math.floor(hours / 24) + "d"
}

function absoluteLocalTime(value) {
  var timestamp = Date.parse(String(value || ""))
  return isNaN(timestamp) ? "" : new Date(timestamp).toLocaleString()
}

function activityLabel(activity) {
  if (activity === "working") return "Working"
  if (activity === "waiting") return "Waiting"
  return ""
}

function taskResultLabel(result, nowMilliseconds) {
  if (!result || result.state === "none") return "Task: None"
  var state = result.state === "succeeded" ? "Succeeded" : "Failed"
  var age = relativeTime(result.completedAt, nowMilliseconds)
  return "Task: " + state + (age ? " · " + age : "")
}



function summary(state, resolutionSource) {
  if (state === "healthy") {
    if (resolutionSource === "node_host") return "Node-host OpenClaw Gateway healthy"
    if (resolutionSource === "configured_remote") return "Remote OpenClaw Gateway healthy"
    return "Local OpenClaw Gateway healthy"
  }
  if (state === "degraded") return "OpenClaw Gateway metadata degraded"
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
    consumeRefresh: consumeRefresh,
    fleetNodes: fleetNodes,
    agents: agents,
    panelRows: panelRows,
    moveFocus: moveFocus,
    workingCount: workingCount,
    relativeTime: relativeTime,
    absoluteLocalTime: absoluteLocalTime,
    activityLabel: activityLabel,
    taskResultLabel: taskResultLabel,
    indexForKey: indexForKey,
    reconcileSelection: reconcileSelection,
    reconcileExpanded: reconcileExpanded
  }
}
