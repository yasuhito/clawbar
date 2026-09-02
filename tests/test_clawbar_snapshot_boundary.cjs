const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")
const Snapshot = require("../ClawbarSnapshot.js")

const widget = fs.readFileSync(path.join(__dirname, "..", "Clawbar.qml"), "utf8")
const streamHandler = widget.match(/onStreamFinished: \{([\s\S]*?)\n      \}/)?.[1] ?? ""
const consumeSnapshotText = new Function("text", "root", "console", streamHandler)

function consume(text, { lastSnapshot = null, collectionAttempted = true, gatewayState = "collecting" } = {}) {
  const warnings = []
  const root = {
    lastSnapshot,
    collectionAttempted,
    gatewayState,
    applySnapshot(snapshot) {
      this.gatewayState = Snapshot.snapshotState(snapshot, Date.now())
      this.lastSnapshot = snapshot
    }
  }

  consumeSnapshotText(text, root, { warn(message) { warnings.push(message) } })
  return { root, warnings }
}

test("壊れた Snapshot はログを出さず No data にする", () => {
  const result = consume("not JSON")

  assert.equal(result.root.gatewayState, "no_data")
  assert.deepEqual(result.warnings, [])
})

test("schema version が違う Snapshot は契約違反の理由をログへ出す", () => {
  const result = consume(JSON.stringify({ schemaVersion: 2, gateway: { state: "healthy" } }))

  assert.equal(result.root.gatewayState, "no_data")
  assert.deepEqual(result.warnings, ["Clawbar rejected Snapshot: Unsupported Clawbar snapshot"])
})

test("Snapshot の契約違反でも既存の表示を保つ", () => {
  const previous = { schemaVersion: 1, gateway: { state: "healthy" } }
  const result = consume(
    JSON.stringify({ schemaVersion: 2, gateway: { state: "healthy" } }),
    { lastSnapshot: previous, gatewayState: "healthy" }
  )

  assert.equal(result.root.gatewayState, "healthy")
  assert.equal(result.root.lastSnapshot, previous)
  assert.deepEqual(result.warnings, ["Clawbar rejected Snapshot: Unsupported Clawbar snapshot"])
})
