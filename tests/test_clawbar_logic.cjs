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
