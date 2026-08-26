// Presentation: labels, time formatting, signal shapes, and the Operational
// Row view-models. Receives plain snapshot data as arguments — the callers
// compose Snapshot.sectionData() with panelSections() so this module carries
// no cross-file imports (works both as a QML JS library and under node:test).

var COMPACT_MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
]

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

function nodeMetadataLabel(item) {
  var parts = [item && item.platform, item && item.model, item && item.version]
    .filter(function(value) { return !!value })
  return parts.length > 0 ? parts.join(" · ") : "No additional Operational Metadata"
}

function showNodeStatusLabel(state, historical) {
  return historical || state !== "healthy"
}

// Operational Row view-models: presentation facts computed once, tested here,
// consumed uniformly by RowSection.qml regardless of kind.

function candidateViewModel(item) {
  return {
    kind: "candidate",
    key: String(item.key || ""),
    item: item,
    name: String(item.name || ""),
    dot: null,
    titleBold: true,
    titleMuted: false,
    statusLabel: "Verify",
    showStatusLabel: true,
    statusCapRatio: null,
    hasSub: false,
    subText: function() { return "" },
    subCritical: false,
    accessibleDescription: "Gateway candidate",
    historical: false,
    observedAt: ""
  }
}

function nodeViewModel(item, historical, observedAt) {
  var signal = nodeSignalPresentation(item.state)
  var offline = item.state === "offline"
  var label = historical ? "Last known" : signal.label
  return {
    kind: "node",
    key: String(item.key || ""),
    item: item,
    name: String(item.name || ""),
    dot: { shape: signal.shape, tone: signal.tone },
    titleBold: !offline,
    titleMuted: offline,
    statusLabel: label,
    showStatusLabel: showNodeStatusLabel(item.state, historical),
    statusCapRatio: null,
    hasSub: false,
    subText: function() { return "" },
    subCritical: false,
    accessibleDescription: label,
    historical: historical,
    observedAt: observedAt
  }
}

function agentViewModel(item, historical, observedAt) {
  var result = item.taskResult || {}
  var failed = result.state === "failed"
  return {
    kind: "agent",
    key: String(item.key || "agent:" + item.name),
    item: item,
    name: String(item.name || ""),
    dot: SIGNAL_PRESENTATIONS.registered_agent,
    titleBold: true,
    titleMuted: false,
    statusLabel: "",
    showStatusLabel: false,
    statusCapRatio: null,
    hasSub: true,
    subText: function(nowMilliseconds) {
      return taskResultLabel(result, nowMilliseconds)
    },
    subCritical: failed,
    accessibleDescription: "Registered Agent",
    historical: historical,
    observedAt: observedAt
  }
}

function automationViewModel(item, historical, observedAt) {
  var failed = !!item.enabled && item.lastResult === "error"
  var disabled = !item.enabled
  var signalState = failed ? "failed" : disabled ? "disabled" : item.lastResult === "ok" ? "succeeded" : "healthy"
  var signal = signalPresentation(signalState)
  return {
    kind: "automation",
    key: item.id ? "automation:" + item.id : "",
    item: item,
    name: String(item.name || ""),
    dot: { shape: signal.shape, tone: signal.tone },
    titleBold: !!item.enabled,
    titleMuted: disabled,
    statusLabel: historical ? "Last known" : automationCompactStatusLabel(item),
    showStatusLabel: showAutomationStatusLabel(item, historical),
    statusCapRatio: 0.42,
    hasSub: true,
    subText: function(nowMilliseconds) {
      if (!historical)
        return automationTimingLabel(item, nowMilliseconds)
      var last = relativeTime(item.lastRunAt, nowMilliseconds)
      return last ? "Last " + last : "No runs yet"
    },
    subCritical: false,
    accessibleDescription: historical ? "Last known" : automationStatusLabel(item),
    historical: historical,
    observedAt: observedAt
  }
}

// Builds the four Operational Row sections from Snapshot.sectionData() output.
function panelSections(data) {
  return [
    {
      kind: "candidate",
      rows: data.candidates.map(function(item, index) {
        return candidateViewModel(item)
      })
    },
    {
      kind: "node",
      rows: data.nodes.map(function(item, index) {
        return nodeViewModel(item, data.historical, data.observedAt)
      })
    },
    {
      kind: "agent",
      rows: data.agents.map(function(item, index) {
        return agentViewModel(item, data.historical, data.observedAt)
      })
    },
    {
      kind: "automation",
      rows: data.automations.map(function(item, index) {
        return automationViewModel(item, data.historical, data.observedAt)
      })
    }
  ]
}

function sectionRows(sections, kind) {
  for (var i = 0; i < sections.length; i++)
    if (sections[i].kind === kind) return sections[i].rows
  return []
}

function sectionKeys(sections) {
  var keys = []
  sections.forEach(function(section) {
    section.rows.forEach(function(row) { keys.push(row.key) })
  })
  return keys
}

function keyKind(sections, key) {
  if (!key) return ""
  for (var i = 0; i < sections.length; i++)
    if (sections[i].rows.some(function(row) { return row.key === key }))
      return sections[i].kind
  return ""
}

function indexForKey(rows, key) {
  if (!key) return -1
  for (var i = 0; i < rows.length; i++) {
    var entryKey = rows[i] && typeof rows[i] === "object" ? rows[i].key : rows[i]
    if (entryKey === key) return i
  }
  return -1
}

function reconcileSelection(rows, selectedKey, indexHint) {
  if (rows.length === 0) return { key: "", index: -1 }
  var retained = indexForKey(rows, selectedKey)
  var index = retained >= 0 ? retained : Math.max(0, Math.min(indexHint, rows.length - 1))
  var entry = rows[index]
  return { key: entry && typeof entry === "object" ? entry.key : entry, index: index }
}

function moveFocus(index, count, delta) {
  if (count <= 0) return -1
  var current = index >= 0 && index < count ? index : 0
  return ((current + delta) % count + count) % count
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

function refreshSummary(baseSummary, feedback, hasSnapshot) {
  if (feedback === "refreshing") return "Refreshing… · " + baseSummary
  if (feedback === "failed" && hasSnapshot) return "Refresh failed · showing last known"
  return baseSummary
}

function metadataUnavailableText(section) {
  return !!section && !section.available && section.reason === "output_exceeded_limit"
    ? "Unavailable — metadata response exceeded the collection limit"
    : null
}

if (typeof module !== "undefined") {
  module.exports = {
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
    signalPresentation: signalPresentation,
    nodeSignalPresentation: nodeSignalPresentation,
    panelSignal: panelSignal,
    configurationGuidance: configurationGuidance,
    nodeMetadataLabel: nodeMetadataLabel,
    showNodeStatusLabel: showNodeStatusLabel,
    panelSections: panelSections,
    sectionRows: sectionRows,
    sectionKeys: sectionKeys,
    keyKind: keyKind,
    indexForKey: indexForKey,
    reconcileSelection: reconcileSelection,
    moveFocus: moveFocus,
    summary: summary,
    panelSummary: panelSummary,
    refreshSummary: refreshSummary,
    metadataUnavailableText: metadataUnavailableText
  }
}
