const test = require("node:test")
const assert = require("node:assert/strict")
const Logic = require("../ClawbarLogic.js")

function healthySnapshot(generatedAt, refreshIntervalSeconds = 30) {
  return {
    schemaVersion: 1,
    generatedAt,
    refreshIntervalSeconds,
    resolutionSource: "local",
    gateway: { state: "healthy" }
  }
}

test("configuration errors render distinctly", () => {
  const snapshot = healthySnapshot(new Date(100000).toISOString())
  snapshot.gateway.state = "configuration_error"

  assert.equal(Logic.snapshotState(snapshot, 100000), "configuration_error")
  assert.equal(Logic.summary("configuration_error", "local"), "OpenClaw Gateway configuration error")
})

test("healthy snapshots become stale after three refresh intervals", () => {
  const snapshot = healthySnapshot(new Date(100000).toISOString())

  assert.equal(Logic.snapshotState(snapshot, 190000), "healthy")
  assert.equal(Logic.snapshotState(snapshot, 190001), "stale")
  assert.equal(Logic.summary("stale", "local"), "OpenClaw Gateway snapshot stale")
})
test("stale timing takes precedence over an old Offline Gateway", () => {
  const snapshot = healthySnapshot(new Date(100000).toISOString())
  snapshot.gateway.state = "offline"
  snapshot.bar = { kind: "attention", count: 1, severity: "critical" }

  assert.equal(Logic.snapshotState(snapshot, 190000), "offline")
  assert.equal(Logic.snapshotState(snapshot, 190001), "stale")
  assert.equal(Logic.barSeverity(snapshot, "stale"), "warning")
  assert.equal(Logic.barCount(snapshot, "stale"), 1)
})

test("first collection exposes Collecting then No data yet", () => {
  const snapshot = healthySnapshot(new Date(100000).toISOString())
  snapshot.gateway.state = "no_data"
  snapshot.bar = { kind: "attention", count: 0, severity: "warning" }

  assert.equal(Logic.summary("collecting", "unresolved", 0, "warning"), "Collecting OpenClaw Gateway status")
  assert.equal(Logic.snapshotState(snapshot, 100000), "no_data")
  assert.equal(Logic.summary("no_data", "unresolved", 0, "warning"), "No OpenClaw Gateway data yet")
  assert.equal(Logic.barCount(snapshot, "no_data"), 0)
})

test("stale and failed collections render retained rows as historical", () => {
  const observedAt = new Date(100000).toISOString()
  const fleet = { available: true, nodes: [{ key: "node:old", name: "studio", state: "offline" }] }
  const agents = { available: true, items: [{ key: "agent:old", name: "planner", activity: "working" }] }
  const automations = {
    available: true,
    items: [{ id: "cron-old", name: "Morning review", enabled: true, lastResult: "error" }]
  }
  const stale = healthySnapshot(observedAt)
  Object.assign(stale, {
    fleet,
    agents,
    automations,
    bar: { kind: "attention", count: 3, severity: "critical" }
  })

  assert.equal(Logic.snapshotState(stale, 190001), "stale")
  assert.equal(Logic.barSeverity(stale, "stale"), "warning")
  assert.equal(Logic.barCount(stale, "stale"), 1)
  assert.deepEqual(
    Logic.panelRows(stale, "stale").map(row => [row.kind, row.historical, row.observedAt]),
    [
      ["node", true, observedAt],
      ["agent", true, observedAt],
      ["automation", true, observedAt]
    ]
  )

  const failed = {
    ...healthySnapshot(new Date(130000).toISOString()),
    gateway: { state: "unstable" },
    fleet: { available: false, nodes: [] },
    agents: { available: false, items: [] },
    automations: { available: false, items: [] },
    bar: { kind: "attention", count: 1, severity: "warning" },
    lastKnown: { observedAt, gateway: { state: "healthy" }, fleet, agents, automations }
  }
  assert.deepEqual(Logic.fleetNodes(failed, "unstable"), fleet.nodes)
  assert.equal(Logic.panelRows(failed, "unstable")[0].historical, true)
  assert.equal(Logic.barCount(failed, "unstable"), 1)
  assert.equal(Logic.snapshotState(failed, 220001), "stale")
  assert.deepEqual(Logic.fleetNodes(failed, "stale"), fleet.nodes)
  assert.equal(Logic.observationTime(failed, "stale"), observedAt)
})


test("refresh interval normalization uses one policy", () => {
  assert.equal(Logic.normalizeRefreshInterval("15"), 15)
  assert.equal(Logic.normalizeRefreshInterval("300"), 300)
  assert.equal(Logic.normalizeRefreshInterval("14"), 30)
  assert.equal(Logic.normalizeRefreshInterval("301"), 30)
  assert.equal(Logic.normalizeRefreshInterval("30.5"), 30)
  assert.equal(Logic.normalizeRefreshInterval("invalid"), 30)
})

test("queued refreshes coalesce and wait for a stopped process", () => {
  let requested = Logic.requestRefresh(true)
  assert.deepEqual(requested, { start: false, pending: true })

  requested = Logic.requestRefresh(true)
  assert.deepEqual(requested, { start: false, pending: true })

  const stillRunning = Logic.consumeRefresh(true, requested.pending)
  assert.deepEqual(stillRunning, { wait: true, start: false, pending: true })

  const stopped = Logic.consumeRefresh(false, stillRunning.pending)
  assert.deepEqual(stopped, { wait: false, start: true, pending: false })
})

test("degraded snapshots preserve core reachability until stale", () => {
  const snapshot = healthySnapshot(new Date(100000).toISOString())
  snapshot.gateway.state = "degraded"

  assert.equal(Logic.snapshotState(snapshot, 190000), "degraded")
  assert.equal(Logic.snapshotState(snapshot, 190001), "stale")
  assert.equal(Logic.summary("degraded", "local"), "OpenClaw Gateway metadata degraded")
  snapshot.bar = { kind: "attention", count: 2, severity: "critical" }
  assert.equal(Logic.barSeverity(snapshot, "degraded"), "critical")
  assert.equal(Logic.barCount(snapshot, "degraded"), 2)
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

  const rows = Logic.panelRows(snapshot)

  assert.deepEqual(rows.map(row => `${row.kind}:${row.item.name}`), [
    "node:Local",
    "node:studio-ops",
    "agent:planner",
    "agent:builder"
  ])
  assert.equal(Logic.moveFocus(-1, rows.length, 1), 1)
  assert.equal(Logic.moveFocus(3, rows.length, 1), 0)
  assert.equal(Logic.moveFocus(0, rows.length, -1), 3)
  assert.equal(Logic.moveFocus(0, 0, 1), -1)
})

test("keyless Nodes never receive positional identity", () => {
  const snapshot = healthySnapshot(new Date(100000).toISOString())
  snapshot.fleet = {
    available: true,
    nodes: [{ name: "Local" }, { name: "studio-ops" }]
  }

  const rows = Logic.panelRows(snapshot)

  assert.deepEqual(rows.map(row => row.key), ["", ""])
  assert.equal(Logic.indexForKey(rows, ""), -1)
})

test("Agent Activity remains independent from previous Task Result", () => {
  const completedAt = new Date(100000).toISOString()
  const snapshot = healthySnapshot(completedAt)
  snapshot.agents = {
    available: true,
    items: [
      {
        name: "planner",
        activity: "working",
        taskResult: { state: "failed", completedAt }
      },
      {
        name: "observer",
        activity: "idle",
        taskResult: { state: "succeeded", completedAt }
      },
      {
        name: "indexer",
        activity: "idle",
        taskResult: { state: "none" }
      }
    ]
  }

  assert.equal(
    Logic.taskResultLabel(snapshot.agents.items[0].taskResult, 100000 + 9 * 60000),
    "Task: Failed · 9m"
  )
  assert.equal(Logic.taskResultLabel(snapshot.agents.items[2].taskResult, 100000), "Task: None")
  const observerRow = Logic.panelRows(snapshot).find(row => row.item.name === "observer")
  assert.equal(observerRow.timestamp, completedAt)
  assert.equal(observerRow.missingTimestampLabel, "No completion timestamp")
})

test("Node selection follows stable keys without expansion state", () => {
  const firstRows = Logic.panelRows({
    fleet: {
      available: true,
      nodes: [
        { key: "node:a", name: "MacBook Pro" },
        { key: "node:b", name: "MacBook Pro" }
      ]
    },
    agents: { available: true, items: [] }
  })
  const reorderedRows = [firstRows[1], firstRows[0]]

  const retained = Logic.reconcileSelection(reorderedRows, "node:b", 1)
  const removed = Logic.reconcileSelection([firstRows[0]], retained.key, retained.index)

  assert.deepEqual(retained, { key: "node:b", index: 0 })
  assert.deepEqual(removed, { key: "node:a", index: 0 })
  assert.equal(firstRows[0].missingTimestampLabel, "No observation timestamp")
  assert.notEqual(firstRows[0].key, firstRows[1].key)
})

test("Node metadata label keeps available Operational Metadata", () => {
  assert.equal(
    Logic.nodeMetadataLabel({
      platform: "macOS 26.5.1",
      model: "MacBookPro18,3",
      version: "2026.7.1"
    }),
    "macOS 26.5.1 · MacBookPro18,3 · 2026.7.1"
  )
  assert.equal(Logic.nodeMetadataLabel({ platform: "linux" }), "linux")
  assert.equal(Logic.nodeMetadataLabel({}), "No additional Operational Metadata")
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

  const rows = Logic.panelRows(snapshot)

  assert.deepEqual(rows.map(row => `${row.kind}:${row.item.name}`), [
    "node:Local",
    "agent:planner",
    "automation:Failed",
    "automation:Successful"
  ])
  assert.equal(rows[2].key, "automation:failure-id")
  const reordered = rows.slice(0, 2).concat([rows[3], rows[2]])
  assert.deepEqual(
    Logic.reconcileSelection(reordered, "automation:failure-id", 2),
    { key: "automation:failure-id", index: 3 }
  )
})

test("Automation labels distinguish every accepted state", () => {
  const now = Date.parse("2026-08-22T12:00:00Z")
  const oneHourAgo = "2026-08-22T11:00:00Z"
  const oneHourAhead = "2026-08-22T13:00:00Z"

  assert.equal(
    Logic.automationStatusLabel({ enabled: true, lastResult: "error", consecutiveFailures: 3 }),
    "Automation Failure · 3 consecutive failures"
  )
  assert.equal(
    Logic.automationCompactStatusLabel({ enabled: true, lastResult: "error", consecutiveFailures: 78 }),
    "Failed · 78×"
  )
  assert.equal(
    Logic.automationCompactStatusLabel({ enabled: true, lastResult: "error", consecutiveFailures: 1 }),
    "Failed"
  )
  assert.equal(Logic.automationCompactStatusLabel({ enabled: true, lastResult: "ok" }), "Healthy")
  assert.equal(Logic.automationCompactStatusLabel({ enabled: false, lastResult: "error" }), "Disabled")
  assert.equal(Logic.automationStatusLabel({ enabled: true, lastResult: "skipped" }), "Skipped")
  assert.equal(Logic.automationStatusLabel({ enabled: true, lastResult: "none" }), "No runs yet")
  assert.equal(
    Logic.automationStatusLabel({ enabled: true, kind: "on-exit", lastResult: "none" }),
    "Waiting for event"
  )
  assert.equal(
    Logic.automationStatusLabel({ enabled: true, kind: "at", lastResult: "ok", nextRunAt: null }),
    "Completed"
  )
  assert.equal(Logic.automationStatusLabel({ enabled: false, lastResult: "error" }), "Disabled")
  assert.equal(
    Logic.automationTimingLabel(
      { enabled: true, nextRunAt: oneHourAhead, lastRunAt: oneHourAgo },
      now
    ),
    "Next 1h · Last 1h"
  )
  assert.equal(
    Logic.automationTimingLabel({ enabled: false, lastRunAt: oneHourAgo }, now),
    "Last 1h"
  )
  assert.equal(Logic.automationKindLabel("cron"), "Scheduled")
  assert.equal(Logic.automationKindLabel("every"), "Repeating")
  assert.equal(Logic.automationKindLabel("at"), "One-time")
  assert.equal(Logic.automationKindLabel("on-exit"), "Event-driven")
})

test("bar uses Attention Items for critical Automation state and Working Agents otherwise", () => {
  const snapshot = healthySnapshot(new Date(100000).toISOString())
  snapshot.bar = { kind: "attention", count: 2, severity: "critical" }

  assert.equal(Logic.snapshotState(snapshot, 100000), "healthy")
  assert.equal(Logic.barSeverity(snapshot, "healthy"), "critical")
  assert.equal(Logic.barCount(snapshot, "healthy"), 2)
  assert.equal(
    Logic.summary("healthy", "local", 2, "critical"),
    "Local OpenClaw Gateway healthy · 2 Attention Items"
  )

  snapshot.bar = { kind: "working_agents", count: 3, severity: "healthy" }
  assert.equal(Logic.snapshotState(snapshot, 100000), "healthy")
  assert.equal(Logic.barSeverity(snapshot, "healthy"), "healthy")
  assert.equal(Logic.barCount(snapshot, "healthy"), 3)
})

test("panel header rolls current Incidents above healthy Gateway state", () => {
  const snapshot = healthySnapshot(new Date(100000).toISOString())
  assert.deepEqual(Logic.panelSignal(snapshot, "healthy"), {
    shape: "circle",
    tone: "healthy",
    label: "Healthy"
  })

  snapshot.bar = { kind: "attention", count: 1, severity: "critical" }
  snapshot.automations = {
    available: true,
    items: [{ enabled: true, lastResult: "error" }]
  }
  assert.deepEqual(Logic.panelSignal(snapshot, "healthy"), {
    shape: "circle",
    tone: "critical",
    label: "Automation Failure"
  })

  snapshot.bar.count = 3
  assert.deepEqual(Logic.panelSignal(snapshot, "healthy"), {
    shape: "circle",
    tone: "critical",
    label: "3 Incidents"
  })
  assert.deepEqual(Logic.panelSignal(snapshot, "degraded"), {
    shape: "circle",
    tone: "critical",
    label: "3 Incidents"
  })
  assert.deepEqual(Logic.panelSignal(snapshot, "offline"), {
    shape: "circle",
    tone: "critical",
    label: "Offline"
  })
})

test("configuration errors provide private-safe repair guidance", () => {
  assert.equal(
    Logic.configurationGuidance("configuration_error"),
    "Target is reachable, but no supported OpenClaw Gateway responded.\n"
      + "Update gateway.remote.url in OpenClaw settings."
  )
  assert.equal(Logic.configurationGuidance("healthy"), "")
})

test("signal semantics follow the prototype dot and color legend", () => {
  for (const [state, tone, label] of [
    ["healthy", "healthy", "Healthy"],
    ["succeeded", "healthy", "Succeeded"],
    ["working", "working", "Working"],
    ["waiting", "warning", "Waiting"],
    ["failed", "critical", "Failed"],
    ["offline", "critical", "Offline"],
    ["degraded", "warning", "Degraded"],
    ["collecting", "warning", "Collecting"],
    ["no_data", "warning", "No data yet"],
    ["starting", "warning", "Starting"],
    ["unexpected", "warning", "Unavailable"]
  ]) {
    assert.deepEqual(Logic.signalPresentation(state), { shape: "circle", tone, label })
  }
  assert.deepEqual(Logic.nodeSignalPresentation("offline"), {
    shape: "circle",
    tone: "muted",
    label: "Offline"
  })
  assert.deepEqual(Logic.signalPresentation("disabled"), { shape: "dotted", tone: "disabled", label: "Disabled" })
  assert.deepEqual(Logic.signalPresentation("idle"), { shape: "none", tone: "idle", label: "" })
  assert.equal(Logic.signalColor("critical", "fg", "accent", "urgent", "dim"), "urgent")
  assert.equal(Logic.signalColor("warning", "fg", "accent", "urgent", "dim"), "accent")
  assert.equal(Logic.signalColor("working", "fg", "accent", "urgent", "dim"), "accent")
  assert.equal(Logic.signalColor("disabled", "fg", "accent", "urgent", "dim"), "dim")
  assert.equal(Logic.signalColor("muted", "fg", "accent", "urgent", "dim"), "dim")
  assert.equal(Logic.signalColor("healthy", "fg", "accent", "urgent", "dim"), "fg")
  assert.equal(Logic.signalColor("healthy", "fg", "accent", "urgent", "dim", "green"), "green")
  assert.equal(Logic.signalColor("warning", "fg", "accent", "urgent", "dim", "green", "yellow"), "yellow")
  assert.equal(Logic.themeColorFromTheme('green = "#879A39"', "green", "fg"), "#879A39")
  assert.equal(Logic.themeColorFromTheme('yellow = "#D0A215"', "yellow", "fg"), "#D0A215")
  assert.equal(Logic.themeColorFromTheme('color2 = "#40A02B"', "green", "fg"), "#40A02B")
  assert.equal(Logic.themeColorFromTheme('color3 = "#DF8E1D"', "yellow", "fg"), "#DF8E1D")
  assert.equal(Logic.themeColorFromTheme("foreground = \"#100F0F\"", "green", "fg"), "fg")
})
