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

function automations(snapshot) {
  return snapshot && snapshot.automations && snapshot.automations.available
    && Array.isArray(snapshot.automations.items) ? snapshot.automations.items : []
}


function nodeRow(item, index) {
  return {
    kind: "node",
    key: String(item.key || ""),
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

function automationRow(item, index) {
  return {
    kind: "automation",
    key: item.id ? "automation:" + item.id : "",
    sectionIndex: index,
    item: item,
    expandable: false,
    typeLabel: "Automation",
    timestamp: item.lastRunAt || "",
    missingTimestampLabel: "No runs yet"
  }
}


function panelRows(snapshot) {
  return fleetNodes(snapshot).map(nodeRow)
    .concat(agents(snapshot).map(agentRow))
    .concat(automations(snapshot).map(automationRow))
}

function indexForKey(rows, key) {
  if (!key) return -1
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

function timeUntil(value, nowMilliseconds) {
  var timestamp = Date.parse(String(value || ""))
  if (isNaN(timestamp)) return ""
  var seconds = Math.max(0, Math.floor((timestamp - nowMilliseconds) / 1000))
  if (seconds < 60) return "now"
  var minutes = Math.floor(seconds / 60)
  if (minutes < 60) return minutes + "m"
  var hours = Math.floor(minutes / 60)
  if (hours < 24) return hours + "h"
  return Math.floor(hours / 24) + "d"
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

function automationStatusLabel(automation) {
  if (!automation || !automation.enabled) return "Disabled"
  if (automation.lastResult === "error") {
    var failures = Math.max(1, Number(automation.consecutiveFailures) || 0)
    return "Automation Failure"
      + (failures > 1 ? " · " + failures + " consecutive failures" : "")
  }
  if (automation.lastResult === "skipped") return "Skipped"
  if (automation.kind === "on-exit" && automation.lastResult === "none")
    return "Waiting for event"
  if (automation.kind === "at" && automation.lastResult === "ok" && !automation.nextRunAt)
    return "Completed"
  if (automation.lastResult === "none") return "No runs yet"
  return "Healthy"
}

function automationKindLabel(kind) {
  if (kind === "cron") return "Scheduled"
  if (kind === "every") return "Repeating"
  if (kind === "at") return "One-time"
  if (kind === "on-exit") return "Event-driven"
  return "Unknown"
}


function automationTimingLabel(automation, nowMilliseconds) {
  if (!automation) return ""
  var parts = []
  if (automation.enabled) {
    var next = timeUntil(automation.nextRunAt, nowMilliseconds)
    if (next) parts.push("Next " + next)
  }
  var last = relativeTime(automation.lastRunAt, nowMilliseconds)
  if (last) parts.push("Last " + last)
  return parts.join(" · ")
}

function barSeverity(snapshot, state) {
  if (state === "offline" || state === "configuration_error") return "critical"
  if (state !== "healthy") return "warning"
  return snapshot && snapshot.bar && snapshot.bar.severity === "critical" ? "critical" : "healthy"
}

function barCount(snapshot, state) {
  var count = snapshot && snapshot.bar ? Number(snapshot.bar.count) : 0
  if (!isFinite(count) || count < 0) count = 0
  if (barSeverity(snapshot, state) !== "healthy") return Math.max(1, Math.floor(count))
  return Math.floor(count)
}




function summary(state, resolutionSource, count, severity) {
  var text
  if (state === "healthy") {
    if (resolutionSource === "node_host") text = "Node-host OpenClaw Gateway healthy"
    else if (resolutionSource === "configured_remote") text = "Remote OpenClaw Gateway healthy"
    else text = "Local OpenClaw Gateway healthy"
  } else if (state === "degraded") text = "OpenClaw Gateway metadata degraded"
  else if (state === "unstable") text = "OpenClaw Gateway unstable"
  else if (state === "offline") text = "OpenClaw Gateway offline"
  else if (state === "configuration_error") text = "OpenClaw Gateway configuration error"
  else if (state === "stale") text = "OpenClaw Gateway snapshot stale"
  else text = "OpenClaw Gateway status unavailable"
  if (severity !== "healthy" && count > 0)
    text += count === 1 ? " · 1 Attention Item" : " · " + count + " Attention Items"
  return text
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
    automations: automations,
    panelRows: panelRows,
    moveFocus: moveFocus,
    relativeTime: relativeTime,
    timeUntil: timeUntil,
    absoluteLocalTime: absoluteLocalTime,
    activityLabel: activityLabel,
    taskResultLabel: taskResultLabel,
    automationStatusLabel: automationStatusLabel,
    automationKindLabel: automationKindLabel,
    automationTimingLabel: automationTimingLabel,
    barSeverity: barSeverity,
    barCount: barCount,
    indexForKey: indexForKey,
    reconcileSelection: reconcileSelection,
    reconcileExpanded: reconcileExpanded
  }
}
