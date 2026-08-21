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
})

test("panel rows preserve Gateway order and keyboard focus wraps", () => {
  const snapshot = healthySnapshot(new Date(100000).toISOString())
  snapshot.fleet = {
    available: true,
    nodes: [{ name: "Local" }, { name: "studio-ops" }]
  }
  snapshot.agents = {
    available: true,
    items: [{ name: "planner" }, { name: "builder" }]
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

  assert.equal(Logic.workingCount(snapshot), 1)
  assert.equal(Logic.activityLabel("working"), "Working")
  assert.equal(Logic.activityLabel("waiting"), "Waiting")
  assert.equal(Logic.activityLabel("idle"), "")
  assert.equal(
    Logic.taskResultLabel(snapshot.agents.items[0].taskResult, 100000 + 9 * 60000),
    "Task: Failed · 9m"
  )
  assert.equal(Logic.taskResultLabel(snapshot.agents.items[2].taskResult, 100000), "Task: None")
  assert.equal(
    Logic.rowTimestamp({ kind: "agent", item: snapshot.agents.items[1] }),
    completedAt
  )
})
