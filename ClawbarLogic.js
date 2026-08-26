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


function candidateRow(item, index) {
  return {
    kind: "candidate",
    key: String(item.key || ""),
    sectionIndex: index,
    item: item,
    typeLabel: "Gateway candidate",
    timestamp: "",
    missingTimestampLabel: "",
    historical: false,
    observedAt: ""
  }
}


function nodeRow(item, index, historical, observedAt) {
  return {
    kind: "node",
    key: String(item.key || ""),
    sectionIndex: index,
    item: item,
    typeLabel: "Node",
    timestamp: item.lastSeenAt || "",
    missingTimestampLabel: "No observation timestamp",
    historical: historical,
    observedAt: observedAt
  }
}

function nodeMetadataLabel(item) {
  var parts = [item && item.platform, item && item.model, item && item.version]
    .filter(function(value) { return !!value })
  return parts.length > 0 ? parts.join(" · ") : "No additional Operational Metadata"
}

function showNodeStatusLabel(state, historical) {
  return historical || state !== "healthy"
}

function agentRow(item, index, historical, observedAt) {
  var result = item.taskResult || {}
  return {
    kind: "agent",
    key: String(item.key || "agent:" + item.name),
    sectionIndex: index,
    item: item,
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
  return setupCandidates(snapshot, state).map(function(item, index) {
    return candidateRow(item, index)
  }).concat(fleetNodes(snapshot, state).map(function(item, index) {
    return nodeRow(item, index, historical, observedAt)
  })).concat(agents(snapshot, state).map(function(item, index) {
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

var COMPACT_MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
]

function compactAbsoluteLocalTime(value, nowMilliseconds) {
  var timestamp = Date.parse(String(value || ""))
  if (isNaN(timestamp)) return ""

  var date = new Date(timestamp)
  var reference = new Date(
    typeof nowMilliseconds === "number" ? nowMilliseconds : Date.now()
  )
  var dateLabel = COMPACT_MONTHS[date.getMonth()] + " " + date.getDate()
  if (date.getFullYear() !== reference.getFullYear())
    dateLabel += ", " + date.getFullYear()

  var hours = String(date.getHours()).padStart(2, "0")
  var minutes = String(date.getMinutes()).padStart(2, "0")
  return dateLabel + ", " + hours + ":" + minutes
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
  registered_agent: { shape: "circle", tone: "registered", label: "Registered Agent" },
  waiting: { shape: "circle", tone: "warning", label: "Waiting" },
  failed: { shape: "circle", tone: "critical", label: "Failed" },
  offline: { shape: "circle", tone: "critical", label: "Offline" },
  node_offline: { shape: "circle", tone: "muted", label: "Offline" },
  configuration_error: { shape: "circle", tone: "critical", label: "Configuration Error" },
  degraded: { shape: "circle", tone: "warning", label: "Degraded" },
  unstable: { shape: "circle", tone: "warning", label: "Unstable" },
  stale: { shape: "circle", tone: "warning", label: "Stale" },
  collecting: { shape: "circle", tone: "warning", label: "Collecting" },
  setup_required: { shape: "circle", tone: "warning", label: "Gateway Setup Required" },
  no_data: { shape: "circle", tone: "warning", label: "No data yet" },
  starting: { shape: "circle", tone: "warning", label: "Starting" },
  unknown: { shape: "circle", tone: "warning", label: "Unavailable" },
  disabled: { shape: "dotted", tone: "disabled", label: "Disabled" }
}

function signalPresentation(state) {
  return SIGNAL_PRESENTATIONS[state] || SIGNAL_PRESENTATIONS.unknown
}

function nodeSignalPresentation(state) {
  return state === "offline" ? SIGNAL_PRESENTATIONS.node_offline : signalPresentation(state)
}

function panelSignal(snapshot, state) {
  var base = signalPresentation(state)
  if ((state !== "healthy" && state !== "degraded") || !snapshot || !snapshot.bar
      || snapshot.bar.severity !== "critical") return base
  var count = Math.max(0, Math.floor(Number(snapshot.bar.count) || 0))
  if (count > 1) return { shape: "circle", tone: "critical", label: count + " Incidents" }
  if (count !== 1) return base
  var automations = snapshot.automations && snapshot.automations.items
  if (Array.isArray(automations) && automations.some(function(item) {
    return item && item.enabled === true && item.lastResult === "error"
  })) return { shape: "circle", tone: "critical", label: "Automation Failure" }
  return { shape: "circle", tone: "critical", label: "1 Incident" }
}

function configurationGuidance(state) {
  if (state !== "configuration_error") return ""
  return "Target is reachable, but no supported OpenClaw Gateway responded.\n"
    + "Update gateway.remote.url in OpenClaw settings."
}

function signalColor(tone, foreground, accent, urgent, dim, healthy, warning) {
  if (tone === "critical") return urgent
  if (tone === "warning") return warning || accent
  if (tone === "registered") return healthy || foreground
  if (tone === "disabled" || tone === "muted") return dim
  if (tone === "healthy" && healthy) return healthy
  return foreground
}

function colorChannels(value) {
  var text = String(value || "").replace(/^#/, "")
  if (/^[0-9a-fA-F]{3}$/.test(text))
    text = text.split("").map(function(part) { return part + part }).join("")
  if (/^[0-9a-fA-F]{8}$/.test(text)) text = text.slice(2)
  if (!/^[0-9a-fA-F]{6}$/.test(text)) return null
  return [0, 2, 4].map(function(offset) {
    return parseInt(text.slice(offset, offset + 2), 16) / 255
  })
}

function colorHex(channels) {
  if (!channels) return "#000000"
  return "#" + channels.map(function(channel) {
    var value = Math.max(0, Math.min(255, Math.round(channel * 255))).toString(16)
    return value.length < 2 ? "0" + value : value
  }).join("")
}

function blendColor(foreground, background, amount) {
  var front = colorChannels(foreground)
  var back = colorChannels(background)
  if (!front || !back) return String(foreground || background || "#000000")
  var alpha = Math.max(0, Math.min(1, Number(amount)))
  return colorHex(front.map(function(channel, index) {
    return channel * alpha + back[index] * (1 - alpha)
  }))
}

function colorLuminance(value) {
  var channels = colorChannels(value)
  if (!channels) return 0
  var linear = channels.map(function(channel) {
    return channel <= 0.04045 ? channel / 12.92 : Math.pow((channel + 0.055) / 1.055, 2.4)
  })
  return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722
}

function contrastRatio(first, second) {
  var lighter = Math.max(colorLuminance(first), colorLuminance(second))
  var darker = Math.min(colorLuminance(first), colorLuminance(second))
  return (lighter + 0.05) / (darker + 0.05)
}

function readableColor(preferred, fallback, background, minimumContrast) {
  var preferredChannels = colorChannels(preferred)
  var fallbackChannels = colorChannels(fallback)
  var minimum = Math.max(1, Number(minimumContrast) || 4.5)
  if (!preferredChannels || !fallbackChannels || !colorChannels(background)) return String(fallback)
  var normalized = colorHex(preferredChannels)
  if (contrastRatio(normalized, background) >= minimum) return normalized
  for (var step = 1; step <= 100; step += 1) {
    var candidate = blendColor(fallback, preferred, step / 100)
    if (contrastRatio(candidate, background) >= minimum + 0.02) return candidate
  }
  return colorHex(fallbackChannels)
}

function themeColorFromTheme(raw, name, fallback) {
  var aliases = name === "green" ? ["green", "color2"]
    : name === "yellow" ? ["yellow", "color3"] : [name]
  var text = String(raw || "")
  for (var i = 0; i < aliases.length; i++) {
    var pattern = new RegExp("^\\s*" + aliases[i] + "\\s*=\\s*[\"']?(#[0-9a-f]{6})", "im")
    var match = text.match(pattern)
    if (match) return match[1]
  }
  return fallback
}

function taskResultLabel(result, nowMilliseconds) {
  if (!result || result.state === "none") return "Task: None"
  var state = result.state === "succeeded" ? "Succeeded" : "Failed"
  var age = relativeTime(result.completedAt, nowMilliseconds)
  return "Task: " + state + (age ? " · " + age : "")
}

function automationFailureCount(automation) {
  return Math.max(1, Number(automation && automation.consecutiveFailures) || 0)
}

function automationStatusLabel(automation) {
  if (!automation || !automation.enabled) return "Disabled"
  if (automation.lastResult === "error") {
    var failures = automationFailureCount(automation)
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

function automationCompactStatusLabel(automation) {
  if (automation && automation.enabled && automation.lastResult === "error") {
    var failures = automationFailureCount(automation)
    return "Failed" + (failures > 1 ? " · " + failures + "×" : "")
  }
  return automationStatusLabel(automation)
}

function showAutomationStatusLabel(automation, historical) {
  if (historical || !automation || !automation.enabled) return true
  if (automation.lastResult !== "ok") return true
  return automation.kind === "at" && !automation.nextRunAt
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

function summary(state, resolutionSource, count, severity, includeAttentionCount) {
  var text
  if (state === "healthy") {
    if (resolutionSource === "tailscale") text = "Verified Tailscale OpenClaw Gateway healthy"
    else if (resolutionSource === "node_host") text = "Node-host OpenClaw Gateway healthy"
    else if (resolutionSource === "configured_remote") text = "Remote OpenClaw Gateway healthy"
    else text = "Local OpenClaw Gateway healthy"
  } else if (state === "degraded") text = "OpenClaw Gateway metadata degraded"
  else if (state === "unstable") text = "OpenClaw Gateway unstable"
  else if (state === "offline") text = "OpenClaw Gateway offline"
  else if (state === "configuration_error") text = "OpenClaw Gateway configuration error"
  else if (state === "stale") text = "OpenClaw Gateway snapshot stale"
  else if (state === "collecting") text = "Collecting OpenClaw Gateway status"
  else if (state === "setup_required") text = "OpenClaw Gateway setup required"
  else if (state === "no_data") text = "No OpenClaw Gateway data yet"
  else text = "OpenClaw Gateway status unavailable"
  if (includeAttentionCount !== false && severity !== "healthy" && count > 0)
    text += count === 1 ? " · 1 Attention Item" : " · " + count + " Attention Items"
  return text
}

function panelSummary(state, resolutionSource, count, severity, panelSignalLabel) {
  var headerShowsIncidentCount = /^\d+ Incidents?$/.test(String(panelSignalLabel || ""))
  return summary(state, resolutionSource, count, severity, !headerShowsIncidentCount)
}

function metadataUnavailableText(section) {
  return !!section && !section.available && section.reason === "output_exceeded_limit"
    ? "Unavailable — metadata response exceeded the collection limit"
    : null
}

function refreshSummary(baseSummary, feedback, hasSnapshot) {
  if (feedback === "refreshing") return "Refreshing… · " + baseSummary
  if (feedback === "failed" && hasSnapshot) return "Refresh failed · showing last known"
  return baseSummary
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
    panelSummary: panelSummary,
    refreshSummary: refreshSummary,
    requestRefresh: requestRefresh,
    consumeRefresh: consumeRefresh,
    historicalState: historicalState,
    metadataSnapshot: metadataSnapshot,
    observationTime: observationTime,
    fleetNodes: fleetNodes,
    agents: agents,
    automations: automations,
    setupCandidates: setupCandidates,
    panelRows: panelRows,
    moveFocus: moveFocus,
    relativeTime: relativeTime,
    timeUntil: timeUntil,
    absoluteLocalTime: absoluteLocalTime,
    compactAbsoluteLocalTime: compactAbsoluteLocalTime,
    taskResultLabel: taskResultLabel,
    automationStatusLabel: automationStatusLabel,
    automationCompactStatusLabel: automationCompactStatusLabel,
    showAutomationStatusLabel: showAutomationStatusLabel,
    automationKindLabel: automationKindLabel,
    automationTimingLabel: automationTimingLabel,
    signalColor: signalColor,
    blendColor: blendColor,
    contrastRatio: contrastRatio,
    readableColor: readableColor,
    themeColorFromTheme: themeColorFromTheme,
    signalPresentation: signalPresentation,
    panelSignal: panelSignal,
    configurationGuidance: configurationGuidance,
    barSeverity: barSeverity,
    barCount: barCount,
    indexForKey: indexForKey,
    reconcileSelection: reconcileSelection,
    nodeMetadataLabel: nodeMetadataLabel,
    showNodeStatusLabel: showNodeStatusLabel,
    nodeSignalPresentation: nodeSignalPresentation,
    metadataUnavailableText: metadataUnavailableText
  }
}
