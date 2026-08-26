const test = require("node:test")
const assert = require("node:assert/strict")
const Snapshot = require("../ClawbarSnapshot.js")
const Presentation = require("../ClawbarPresentation.js")

function healthySnapshot(generatedAt, refreshIntervalSeconds = 30) {
  return {
    schemaVersion: 1,
    generatedAt,
    refreshIntervalSeconds,
    resolutionSource: "local",
    gateway: { state: "healthy" }
  }
}

function operationalSnapshot() {
  const snapshot = healthySnapshot(new Date(100000).toISOString())
  snapshot.fleet = {
    available: true,
    nodes: [
      { key: "node:a", name: "alpha", state: "healthy" },
      { key: "node:b", name: "beta", state: "offline" }
    ]
  }
  snapshot.agents = {
    available: true,
    items: [
      { key: "agent:a", name: "planner", taskResult: { state: "failed", completedAt: new Date(50000).toISOString() } },
      { name: "observer" }
    ]
  }
  snapshot.automations = {
    available: true,
    items: [
      { id: "cron-1", name: "Morning review", enabled: true, lastResult: "error", consecutiveFailures: 2 },
      { id: "off-1", name: "Retired job", enabled: false, lastRunAt: new Date(60000).toISOString(), lastResult: "none" }
    ]
  }
  return snapshot
}

test("compact local timestamps stay scan-friendly and retain meaningful dates", () => {
  const current = new Date(2026, 7, 24, 17, 44)
  const previousYear = new Date(2025, 11, 3, 6, 5)

  assert.equal(
    Presentation.compactAbsoluteLocalTime(current.toISOString(), current.getTime()),
    "Aug 24, 17:44"
  )
  assert.equal(
    Presentation.compactAbsoluteLocalTime(previousYear.toISOString(), current.getTime()),
    "Dec 3, 2025, 06:05"
  )
  assert.equal(Presentation.compactAbsoluteLocalTime("invalid", current.getTime()), "")
})

test("panel rows preserve Gateway order and keyboard focus wraps", () => {
  const snapshot = healthySnapshot(new Date(100000).toISOString())
  snapshot.fleet = {
    available: true,
    nodes: [{ key: "node:a", name: "Local" }, { key: "node:b", name: "studio-ops" }]
  }
  snapshot.agents = {
    available: true,
    items: [{ key: "agent:planner", name: "planner" }, { key: "agent:builder", name: "builder" }]
  }

  const sections = Presentation.panelSections(Snapshot.sectionData(snapshot, "healthy"))
  const keys = Presentation.sectionKeys(sections)

  const kinds = sections.flatMap(s => s.rows).map(row => `${row.kind}:${row.item.name}`)
  assert.deepEqual(kinds, [
    "node:Local",
    "node:studio-ops",
    "agent:planner",
    "agent:builder"
  ])
  assert.equal(Presentation.moveFocus(-1, keys.length, 1), 1)
  assert.equal(Presentation.moveFocus(3, keys.length, 1), 0)
  assert.equal(Presentation.moveFocus(0, keys.length, -1), 3)
  assert.equal(Presentation.moveFocus(0, 0, 1), -1)
})

test("keyless Nodes never receive positional identity", () => {
  const snapshot = healthySnapshot(new Date(100000).toISOString())
  snapshot.fleet = {
    available: true,
    nodes: [{ name: "Local" }, { name: "studio-ops" }]
  }

  const nodeKeys = Presentation.sectionRows(Presentation.panelSections(Snapshot.sectionData(snapshot, "healthy")), "node")
    .map(row => row.key)

  assert.deepEqual(nodeKeys, ["", ""])
  assert.equal(Presentation.indexForKey(["", ""], ""), -1)
})

test("registered Agents expose Task Result without claiming current Activity", () => {
  const completedAt = new Date(100000).toISOString()
  const snapshot = healthySnapshot(completedAt)
  snapshot.agents = {
    available: true,
    items: [
      {
        name: "planner",
        taskResult: { state: "failed", completedAt }
      },
      {
        name: "observer",
        taskResult: { state: "succeeded", completedAt }
      },
      {
        name: "indexer",
        taskResult: { state: "none" }
      }
    ]
  }

  assert.equal(
    Presentation.taskResultLabel(snapshot.agents.items[0].taskResult, 100000 + 9 * 60000),
    "Task: Failed · 9m"
  )
  assert.equal(Presentation.taskResultLabel(snapshot.agents.items[2].taskResult, 100000), "Task: None")
  const observerRow = Presentation.panelSections(Snapshot.sectionData(snapshot, "healthy"))
    .flatMap(s => s.rows)
    .find(row => row.item.name === "observer")
  assert.equal(observerRow.key, "agent:observer")
  assert.match(observerRow.subText(100000 + 9 * 60000), /^Task: Succeeded · 9m$/)
})

test("Node selection follows stable keys without expansion state", () => {
  const firstKeys = Presentation.sectionKeys(Presentation.panelSections(Snapshot.sectionData({
    fleet: {
      available: true,
      nodes: [
        { key: "node:a", name: "MacBook Pro" },
        { key: "node:b", name: "MacBook Pro" }
      ]
    },
    agents: { available: true, items: [] }
  }, "healthy"))).filter(key => key.startsWith("node:"))
  const reordered = [firstKeys[1], firstKeys[0]]

  const retained = Presentation.reconcileSelection(reordered, "node:b", 1)
  const removed = Presentation.reconcileSelection([firstKeys[0]], retained.key, retained.index)

  assert.deepEqual(retained, { key: "node:b", index: 0 })
  assert.deepEqual(removed, { key: "node:a", index: 0 })
  assert.notEqual(firstKeys[0], firstKeys[1])
})

test("Node metadata label keeps available Operational Metadata", () => {
  assert.equal(
    Presentation.nodeMetadataLabel({
      platform: "macOS 26.5.1",
      model: "MacBookPro18,3",
      version: "2026.7.1"
    }),
    "macOS 26.5.1 · MacBookPro18,3 · 2026.7.1"
  )
  assert.equal(Presentation.nodeMetadataLabel({ platform: "linux" }), "linux")
  assert.equal(Presentation.nodeMetadataLabel({}), "No additional Operational Metadata")
})

test("Automations follow Agents and retain selection by stable hidden id", () => {
  const snapshot = healthySnapshot(new Date(100000).toISOString())
  snapshot.fleet = { available: true, nodes: [{ key: "node:a", name: "Local" }] }
  snapshot.agents = { available: true, items: [{ key: "agent:planner", name: "planner" }] }
  snapshot.automations = {
    available: true,
    items: [
      { id: "failure-id", name: "Failed", enabled: true, lastResult: "error" },
      { id: "success-id", name: "Successful", enabled: true, lastResult: "ok" }
    ]
  }

  const keys = Presentation.sectionKeys(Presentation.panelSections(Snapshot.sectionData(snapshot, "healthy")))

  assert.deepEqual(keys, [
    "node:a",
    "agent:planner",
    "automation:failure-id",
    "automation:success-id"
  ])
  assert.equal(keys[2], "automation:failure-id")
  const reordered = [keys[0], keys[1], keys[3], keys[2]]
  assert.deepEqual(
    Presentation.reconcileSelection(reordered, "automation:failure-id", 2),
    { key: "automation:failure-id", index: 3 }
  )
})

test("Automation labels distinguish every accepted state", () => {
  const now = Date.parse("2026-08-22T12:00:00Z")
  const oneHourAgo = "2026-08-22T11:00:00Z"
  const oneHourAhead = "2026-08-22T13:00:00Z"

  assert.equal(
    Presentation.automationStatusLabel({ enabled: true, lastResult: "error", consecutiveFailures: 3 }),
    "Automation Failure · 3 consecutive failures"
  )
  assert.equal(
    Presentation.automationCompactStatusLabel({ enabled: true, lastResult: "error", consecutiveFailures: 78 }),
    "Failed · 78×"
  )
  assert.equal(
    Presentation.automationCompactStatusLabel({ enabled: true, lastResult: "error", consecutiveFailures: 1 }),
    "Failed"
  )
  assert.equal(Presentation.automationCompactStatusLabel({ enabled: true, lastResult: "ok" }), "Healthy")
  assert.equal(Presentation.automationCompactStatusLabel({ enabled: false, lastResult: "error" }), "Disabled")
  assert.equal(
    Presentation.automationCompactStatusLabel({ enabled: true, kind: "on-exit", lastResult: "none" }),
    "Waiting for event"
  )
  assert.equal(
    Presentation.automationCompactStatusLabel({ enabled: true, kind: "at", lastResult: "ok", nextRunAt: null }),
    "Completed"
  )
  assert.equal(Presentation.automationStatusLabel({ enabled: true, lastResult: "skipped" }), "Skipped")
  assert.equal(Presentation.automationStatusLabel({ enabled: true, lastResult: "none" }), "No runs yet")
  assert.equal(
    Presentation.automationStatusLabel({ enabled: true, kind: "on-exit", lastResult: "none" }),
    "Waiting for event"
  )
  assert.equal(
    Presentation.automationStatusLabel({ enabled: true, kind: "at", lastResult: "ok", nextRunAt: null }),
    "Completed"
  )
  assert.equal(Presentation.automationStatusLabel({ enabled: false, lastResult: "error" }), "Disabled")
  assert.equal(
    Presentation.automationTimingLabel(
      { enabled: true, nextRunAt: oneHourAhead, lastRunAt: oneHourAgo },
      now
    ),
    "Next 1h · Last 1h"
  )
  assert.equal(
    Presentation.automationTimingLabel({ enabled: false, lastRunAt: oneHourAgo }, now),
    "Last 1h"
  )
  assert.equal(Presentation.automationKindLabel("cron"), "Scheduled")
  assert.equal(Presentation.automationKindLabel("every"), "Repeating")
  assert.equal(Presentation.automationKindLabel("at"), "One-time")
  assert.equal(Presentation.automationKindLabel("on-exit"), "Event-driven")
})

test("healthy row labels stay quiet while actionable states remain explicit", () => {
  assert.equal(Presentation.showNodeStatusLabel("healthy", false), false)
  assert.equal(Presentation.showNodeStatusLabel("offline", false), true)
  assert.equal(Presentation.showNodeStatusLabel("healthy", true), true)

  assert.equal(
    Presentation.showAutomationStatusLabel(
      { enabled: true, kind: "cron", lastResult: "ok", nextRunAt: "2026-08-25T00:00:00Z" },
      false
    ),
    false
  )
  assert.equal(
    Presentation.showAutomationStatusLabel(
      { enabled: true, kind: "at", lastResult: "ok", nextRunAt: null },
      false
    ),
    true
  )
  assert.equal(Presentation.showAutomationStatusLabel({ enabled: true, lastResult: "error" }, false), true)
  assert.equal(Presentation.showAutomationStatusLabel({ enabled: false, lastResult: "ok" }, false), true)
  assert.equal(Presentation.showAutomationStatusLabel({ enabled: true, lastResult: "none" }, false), true)
  assert.equal(Presentation.showAutomationStatusLabel({ enabled: true, lastResult: "ok" }, true), true)
})

test("panel omits a duplicated Attention count only when its header shows an Incident count", () => {
  assert.equal(
    Presentation.panelSummary("healthy", "local", 2, "critical", "2 Incidents"),
    "Local OpenClaw Gateway healthy"
  )
  assert.equal(
    Presentation.panelSummary("healthy", "local", 1, "critical", "1 Incident"),
    "Local OpenClaw Gateway healthy"
  )
  assert.equal(
    Presentation.panelSummary("healthy", "local", 1, "critical", "Automation Failure"),
    "Local OpenClaw Gateway healthy · 1 Attention Item"
  )
  assert.equal(
    Presentation.panelSummary("degraded", "local", 1, "warning", "Degraded"),
    "OpenClaw Gateway metadata degraded · 1 Attention Item"
  )
})

test("manual refresh feedback preserves the current private-safe summary", () => {
  assert.equal(
    Presentation.refreshSummary("Local OpenClaw Gateway healthy", "refreshing", true),
    "Refreshing… · Local OpenClaw Gateway healthy"
  )
  assert.equal(
    Presentation.refreshSummary("Local OpenClaw Gateway healthy", "failed", true),
    "Refresh failed · showing last known"
  )
  assert.equal(
    Presentation.refreshSummary("No OpenClaw Gateway data yet", "failed", false),
    "No OpenClaw Gateway data yet"
  )
  assert.equal(
    Presentation.refreshSummary("Local OpenClaw Gateway healthy", "idle", true),
    "Local OpenClaw Gateway healthy"
  )
})

test("panel header rolls current Incidents above healthy Gateway state", () => {
  const snapshot = healthySnapshot(new Date(100000).toISOString())
  assert.deepEqual(Presentation.panelSignal(snapshot, "healthy"), {
    shape: "circle",
    tone: "healthy",
    label: "Healthy"
  })

  snapshot.bar = { kind: "attention", count: 1, severity: "critical" }
  snapshot.automations = {
    available: true,
    items: [{ enabled: true, lastResult: "error" }]
  }
  assert.deepEqual(Presentation.panelSignal(snapshot, "healthy"), {
    shape: "circle",
    tone: "critical",
    label: "Automation Failure"
  })

  snapshot.bar.count = 3
  assert.deepEqual(Presentation.panelSignal(snapshot, "healthy"), {
    shape: "circle",
    tone: "critical",
    label: "3 Incidents"
  })
  assert.deepEqual(Presentation.panelSignal(snapshot, "degraded"), {
    shape: "circle",
    tone: "critical",
    label: "3 Incidents"
  })
  assert.deepEqual(Presentation.panelSignal(snapshot, "offline"), {
    shape: "circle",
    tone: "critical",
    label: "Offline"
  })
})

test("configuration errors provide private-safe repair guidance", () => {
  assert.equal(
    Presentation.configurationGuidance("configuration_error"),
    "Target is reachable, but no supported OpenClaw Gateway responded.\n"
      + "Update gateway.remote.url in OpenClaw settings."
  )
  assert.equal(Presentation.configurationGuidance("healthy"), "")
})

test("signal semantics follow the prototype dot and color legend", () => {
  for (const [state, tone, label] of [
    ["healthy", "healthy", "Healthy"],
    ["succeeded", "healthy", "Succeeded"],
    ["waiting", "warning", "Waiting"],
    ["failed", "critical", "Failed"],
    ["offline", "critical", "Offline"],
    ["degraded", "warning", "Degraded"],
    ["collecting", "warning", "Collecting"],
    ["no_data", "warning", "No data yet"],
    ["starting", "warning", "Starting"],
    ["unexpected", "warning", "Unavailable"]
  ]) {
    assert.deepEqual(Presentation.signalPresentation(state), { shape: "circle", tone, label })
  }
  assert.deepEqual(Presentation.nodeSignalPresentation("offline"), {
    shape: "circle",
    tone: "muted",
    label: "Offline"
  })
  assert.deepEqual(Presentation.signalPresentation("registered_agent"), {
    shape: "circle",
    tone: "registered",
    label: "Registered Agent"
  })
  assert.deepEqual(Presentation.signalPresentation("disabled"), { shape: "dotted", tone: "disabled", label: "Disabled" })
})

test("metadataUnavailableText maps the size-limit reason to a specific message", () => {
  assert.equal(
    Presentation.metadataUnavailableText({
      available: false,
      reason: "output_exceeded_limit",
    }),
    "Unavailable — metadata response exceeded the collection limit"
  )
})

test("metadataUnavailableText returns null without the size-limit reason", () => {
  assert.equal(Presentation.metadataUnavailableText({ available: false }), null)
  assert.equal(
    Presentation.metadataUnavailableText({ available: false, reason: "more_than_500" }),
    null
  )
  assert.equal(Presentation.metadataUnavailableText(null), null)
})

test("panelSections orders candidate, node, agent and automation rows", () => {
  const sections = Presentation.panelSections(Snapshot.sectionData(operationalSnapshot(), "healthy"))

  assert.deepEqual(sections.map(section => section.kind), ["candidate", "node", "agent", "automation"])
  const [candidates, nodes, agents, automations] = sections
  assert.deepEqual(candidates.rows.map(row => row.key), [])
  assert.deepEqual(nodes.rows.map(row => row.key), ["node:a", "node:b"])

  const alpha = nodes.rows[0]
  assert.equal(alpha.showStatusLabel, false)
  assert.equal(alpha.titleMuted, false)
  assert.equal(alpha.titleBold, true)

  const beta = nodes.rows[1]
  assert.equal(beta.dot.tone, "muted")
  assert.equal(beta.dot.shape, "circle")
  assert.equal(beta.titleMuted, true)
  assert.equal(beta.titleBold, false)
  assert.equal(beta.showStatusLabel, true)
  assert.equal(beta.statusLabel, "Offline")
  assert.equal(beta.accessibleDescription, "Offline")

  const planner = agents.rows[0]
  assert.equal(planner.key, "agent:a")
  assert.equal(planner.dot.tone, "registered")
  assert.equal(planner.subCritical, true)
  assert.match(planner.subText(new Date(140000).getTime()), /^Task: Failed/)

  const observer = agents.rows[1]
  assert.equal(observer.key, "agent:observer")
  assert.equal(observer.subCritical, false)

  const failing = automations.rows[0]
  assert.equal(failing.dot.tone, "critical")
  assert.equal(failing.showStatusLabel, true)
  assert.equal(failing.statusLabel, "Failed · 2×")
  assert.equal(failing.accessibleDescription, "Automation Failure · 2 consecutive failures")
  assert.equal(typeof failing.subText(new Date(140000).getTime()), "string")

  const retired = automations.rows[1]
  assert.equal(retired.titleMuted, true)
  assert.equal(retired.dot.tone, "disabled")
  assert.equal(retired.dot.shape, "dotted")
  assert.equal(retired.statusLabel, "Disabled")
})

test("setup candidate rows expose verify actions without dots", () => {
  const snapshot = operationalSnapshot()
  snapshot.gateway.state = "configuration_error"
  snapshot.setup = { candidates: [{ key: "cand-1", name: "mac-studio" }] }

  const state = Snapshot.snapshotState(snapshot, 100000)
  assert.equal(state, "configuration_error")

  const [candidates] = Presentation.panelSections(Snapshot.sectionData(snapshot, state))
  assert.deepEqual(candidates.rows.map(row => row.key), ["cand-1"])
  const row = candidates.rows[0]
  assert.equal(row.dot, null)
  assert.equal(row.name, "mac-studio")
  assert.equal(row.showStatusLabel, true)
  assert.equal(row.statusLabel, "Verify")
  assert.equal(row.historical, false)
})

test("stale snapshots mark every operational row as Last known", () => {
  const observedAt = new Date(100000).toISOString()
  const snapshot = healthySnapshot(observedAt)
  snapshot.lastKnown = {
    observedAt,
    fleet: { available: true, nodes: [{ key: "node:a", name: "alpha", state: "offline" }] },
    agents: { available: true, items: [] },
    automations: { available: true, items: [] }
  }

  const nodes = Presentation.panelSections(Snapshot.sectionData(snapshot, "stale")).find(s => s.kind === "node")
  const row = nodes.rows[0]
  assert.equal(row.historical, true)
  assert.equal(row.observedAt, observedAt)
  assert.equal(row.statusLabel, "Last known")
  assert.equal(row.accessibleDescription, "Last known")
  assert.equal(row.dot.tone, "muted")
})

test("sectionKeys flattens selection order across kinds", () => {
  const sections = [
    { kind: "candidate", rows: [{ key: "c1" }] },
    { kind: "node", rows: [{ key: "n1" }, { key: "n2" }] },
    { kind: "agent", rows: [] },
    { kind: "automation", rows: [{ key: "a1" }] }
  ]

  assert.deepEqual(Presentation.sectionKeys(sections), ["c1", "n1", "n2", "a1"])
})

test("selection reconciliation accepts plain key arrays", () => {
  assert.deepEqual(Presentation.reconcileSelection(["n1", "n2"], "", 1), { key: "n2", index: 1 })
  assert.deepEqual(Presentation.reconcileSelection(["n1"], "missing", 5), { key: "n1", index: 0 })
})
