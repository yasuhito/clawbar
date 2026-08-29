const test = require("node:test")
const assert = require("node:assert/strict")
const Snapshot = require("../ClawbarSnapshot.js")
const Presentation = require("../ClawbarPresentation.js")
const snapshotFixtures = require("./fixtures/snapshots.json")

function healthySnapshot(generatedAt, refreshIntervalSeconds = 30) {
  const snapshot = structuredClone(snapshotFixtures.healthy)
  snapshot.generatedAt = generatedAt
  snapshot.lastSuccessAt = generatedAt
  snapshot.refreshIntervalSeconds = refreshIntervalSeconds
  return snapshot
}

test("configuration errors render distinctly", () => {
  const snapshot = healthySnapshot(new Date(100000).toISOString())
  snapshot.gateway.state = "configuration_error"

  assert.equal(Snapshot.snapshotState(snapshot, 100000), "configuration_error")
  assert.equal(Presentation.summary("configuration_error", "local"), "OpenClaw Gateway configuration error")
})

test("configuration errors use the same Snapshot shape as other failures", () => {
  const snapshot = structuredClone(snapshotFixtures["configuration-error"])

  for (const section of ["fleet", "agents", "automations"]) {
    assert.deepEqual(snapshot[section], {
      available: false,
      [section === "fleet" ? "nodes" : "items"]: []
    })
  }
  assert.deepEqual(snapshot.bar, { kind: "attention", count: 1, severity: "critical" })
})

test("healthy snapshots become stale after three refresh intervals", () => {
  const snapshot = healthySnapshot(new Date(100000).toISOString())

  assert.equal(Snapshot.snapshotState(snapshot, 190000), "healthy")
  assert.equal(Snapshot.snapshotState(snapshot, 190001), "stale")
  assert.equal(Presentation.summary("stale", "local"), "OpenClaw Gateway snapshot stale")
})

test("stale timing takes precedence over an old Offline Gateway", () => {
  const snapshot = healthySnapshot(new Date(100000).toISOString())
  snapshot.gateway.state = "offline"
  snapshot.bar = { kind: "attention", count: 1, severity: "critical" }

  assert.equal(Snapshot.snapshotState(snapshot, 190000), "offline")
  assert.equal(Snapshot.snapshotState(snapshot, 190001), "stale")
  assert.equal(Snapshot.barSeverity(snapshot, "stale"), "warning")
  assert.equal(Snapshot.barCount(snapshot, "stale"), 1)
})

test("first collection exposes Collecting then No data yet", () => {
  const snapshot = healthySnapshot(new Date(100000).toISOString())
  snapshot.gateway.state = "no_data"
  snapshot.bar = { kind: "attention", count: 0, severity: "warning" }

  assert.equal(Presentation.summary("collecting", "unresolved", 0, "warning"), "Collecting OpenClaw Gateway status")
  assert.equal(Snapshot.snapshotState(snapshot, 100000), "no_data")
  assert.equal(Presentation.summary("no_data", "unresolved", 0, "warning"), "No OpenClaw Gateway data yet")
  assert.equal(Snapshot.barCount(snapshot, "no_data"), 0)
})

test("stale and failed collections render retained rows as historical", () => {
  const observedAt = new Date(100000).toISOString()
  const fleet = { available: true, nodes: [{ key: "node:old", name: "studio", state: "offline" }] }
  const agents = { available: true, items: [{ key: "agent:old", name: "planner" }] }
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

  assert.equal(Snapshot.snapshotState(stale, 190001), "stale")
  assert.equal(Snapshot.barSeverity(stale, "stale"), "warning")
  assert.equal(Snapshot.barCount(stale, "stale"), 1)
  assert.deepEqual(
    Presentation.panelSections(Snapshot.sectionData(stale, "stale")).flatMap(s => s.rows).map(row => [row.kind, row.historical, row.observedAt]),
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
  assert.deepEqual(Snapshot.fleetNodes(failed, "unstable"), fleet.nodes)
  assert.equal(Presentation.panelSections(Snapshot.sectionData(failed, "unstable")).flatMap(s => s.rows)[0].historical, true)
  assert.equal(Snapshot.barCount(failed, "unstable"), 1)
  assert.equal(Snapshot.snapshotState(failed, 220001), "stale")
  assert.deepEqual(Snapshot.fleetNodes(failed, "stale"), fleet.nodes)
  assert.equal(Snapshot.observationTime(failed, "stale"), observedAt)
})

test("refresh interval normalization uses one policy", () => {
  assert.equal(Snapshot.normalizeRefreshInterval("15"), 15)
  assert.equal(Snapshot.normalizeRefreshInterval("300"), 300)
  assert.equal(Snapshot.normalizeRefreshInterval("14"), 30)
  assert.equal(Snapshot.normalizeRefreshInterval("301"), 30)
  assert.equal(Snapshot.normalizeRefreshInterval("30.5"), 30)
  assert.equal(Snapshot.normalizeRefreshInterval("invalid"), 30)
})

test("queued refreshes coalesce and wait for a stopped process", () => {
  let requested = Snapshot.requestRefresh(true)
  assert.deepEqual(requested, { start: false, pending: true })

  requested = Snapshot.requestRefresh(true)
  assert.deepEqual(requested, { start: false, pending: true })

  const stillRunning = Snapshot.consumeRefresh(true, requested.pending)
  assert.deepEqual(stillRunning, { wait: true, start: false, pending: true })

  const stopped = Snapshot.consumeRefresh(false, stillRunning.pending)
  assert.deepEqual(stopped, { wait: false, start: true, pending: false })
})

test("degraded snapshots preserve core reachability until stale", () => {
  const snapshot = healthySnapshot(new Date(100000).toISOString())
  snapshot.gateway.state = "degraded"

  assert.equal(Snapshot.snapshotState(snapshot, 190000), "degraded")
  assert.equal(Snapshot.snapshotState(snapshot, 190001), "stale")
  assert.equal(Presentation.summary("degraded", "local"), "OpenClaw Gateway metadata degraded")
  snapshot.bar = { kind: "attention", count: 2, severity: "critical" }
  assert.equal(Snapshot.barSeverity(snapshot, "degraded"), "critical")
  assert.equal(Snapshot.barCount(snapshot, "degraded"), 2)
})

test("bar uses Attention Items and ignores legacy Working Agent counts", () => {
  const snapshot = healthySnapshot(new Date(100000).toISOString())
  snapshot.bar = { kind: "attention", count: 2, severity: "critical" }

  assert.equal(Snapshot.snapshotState(snapshot, 100000), "healthy")
  assert.equal(Snapshot.barSeverity(snapshot, "healthy"), "critical")
  assert.equal(Snapshot.barCount(snapshot, "healthy"), 2)
  assert.equal(
    Presentation.summary("healthy", "local", 2, "critical"),
    "Local OpenClaw Gateway healthy · 2 Attention Items"
  )

  snapshot.bar = { kind: "working_agents", count: 3, severity: "healthy" }
  assert.equal(Snapshot.snapshotState(snapshot, 100000), "healthy")
  assert.equal(Snapshot.barSeverity(snapshot, "healthy"), "healthy")
  assert.equal(Snapshot.barCount(snapshot, "healthy"), 0)
})
