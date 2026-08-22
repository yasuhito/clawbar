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
  var supportedStates = ["healthy", "degraded", "unstable", "offline", "configuration_error", "no_data", "unknown"]
  if (supportedStates.indexOf(state) === -1)
    throw new Error("Unsupported Gateway state")
  if (state === "no_data" || state === "unknown") return state

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


function nodeRow(item, index, historical, observedAt) {
  return {
    kind: "node",
    key: String(item.key || ""),
    sectionIndex: index,
    item: item,
    expandable: true,
    typeLabel: "Node",
    timestamp: item.lastSeenAt || "",
    missingTimestampLabel: "No observation timestamp",
    historical: historical,
    observedAt: observedAt
  }
}

function agentRow(item, index, historical, observedAt) {
  var result = item.taskResult || {}
  return {
    kind: "agent",
    key: String(item.key || "agent:" + item.name),
    sectionIndex: index,
    item: item,
    expandable: false,
    typeLabel: "Agent",
    timestamp: result.completedAt || "",
    missingTimestampLabel: "No completion timestamp",
    historical: historical,
    observedAt: observedAt
  }
}

function automationRow(item, index, historical, observedAt) {
  return {
    kind: "automation",
    key: item.id ? "automation:" + item.id : "",
    sectionIndex: index,
    item: item,
    expandable: false,
    typeLabel: "Automation",
    timestamp: item.lastRunAt || "",
    missingTimestampLabel: "No runs yet",
    historical: historical,
    observedAt: observedAt
  }
}


function panelRows(snapshot, state) {
  var historical = historicalState(state)
  var observedAt = observationTime(snapshot, state)
  return fleetNodes(snapshot, state).map(function(item, index) {
    return nodeRow(item, index, historical, observedAt)
  }).concat(agents(snapshot, state).map(function(item, index) {
    return agentRow(item, index, historical, observedAt)
  })).concat(automations(snapshot, state).map(function(item, index) {
    return automationRow(item, index, historical, observedAt)
  }))
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

var SIGNAL_PRESENTATIONS = {
  healthy: { shape: "circle", tone: "healthy", label: "Healthy" },
  succeeded: { shape: "circle", tone: "healthy", label: "Succeeded" },
  working: { shape: "circle", tone: "working", label: "Working" },
  waiting: { shape: "triangle", tone: "warning", label: "Waiting" },
  failed: { shape: "diamond", tone: "critical", label: "Failed" },
  offline: { shape: "diamond", tone: "critical", label: "Offline" },
  configuration_error: { shape: "diamond", tone: "critical", label: "Configuration Error" },
  degraded: { shape: "triangle", tone: "warning", label: "Degraded" },
  unstable: { shape: "triangle", tone: "warning", label: "Unstable" },
  stale: { shape: "triangle", tone: "warning", label: "Stale" },
  collecting: { shape: "triangle", tone: "warning", label: "Collecting" },
  no_data: { shape: "triangle", tone: "warning", label: "No data yet" },
  starting: { shape: "triangle", tone: "warning", label: "Starting" },
  unknown: { shape: "triangle", tone: "warning", label: "Unavailable" },
  disabled: { shape: "dotted", tone: "disabled", label: "Disabled" },
  idle: { shape: "none", tone: "idle", label: "" }
}

function signalPresentation(state) {
  return SIGNAL_PRESENTATIONS[state] || SIGNAL_PRESENTATIONS.unknown
}

function signalColor(tone, foreground, accent, urgent, dim) {
  if (tone === "critical") return urgent
  if (tone === "warning" || tone === "working") return accent
  if (tone === "disabled") return dim
  return foreground
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
  if (state !== "healthy" && state !== "degraded") return "warning"
  if (snapshot && snapshot.bar && snapshot.bar.severity === "critical") return "critical"
  return state === "degraded" ? "warning" : "healthy"
}

function barCount(snapshot, state) {
  if (state === "collecting" || state === "unknown") return 0
  if (state === "stale" || state === "configuration_error") return 1
  var count = snapshot && snapshot.bar ? Number(snapshot.bar.count) : 0
  if (!isFinite(count) || count < 0) count = 0
  count = Math.floor(count)
  if (state === "no_data") return count
  if (barSeverity(snapshot, state) !== "healthy") return Math.max(1, count)
  return count
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
  else if (state === "collecting") text = "Collecting OpenClaw Gateway status"
  else if (state === "no_data") text = "No OpenClaw Gateway data yet"
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
    historicalState: historicalState,
    metadataSnapshot: metadataSnapshot,
    observationTime: observationTime,
    fleetNodes: fleetNodes,
    agents: agents,
    automations: automations,
    panelRows: panelRows,
    moveFocus: moveFocus,
    relativeTime: relativeTime,
    timeUntil: timeUntil,
    absoluteLocalTime: absoluteLocalTime,
    taskResultLabel: taskResultLabel,
    automationStatusLabel: automationStatusLabel,
    automationKindLabel: automationKindLabel,
    automationTimingLabel: automationTimingLabel,
    signalColor: signalColor,
    signalPresentation: signalPresentation,
    barSeverity: barSeverity,
    barCount: barCount,
    indexForKey: indexForKey,
    reconcileSelection: reconcileSelection,
    reconcileExpanded: reconcileExpanded
  }
}
