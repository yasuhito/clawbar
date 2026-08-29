# Orca automation の定義

`clawbar issue coordinator` と `clawbar PR reviewer` は Orca の automation として登録されている。このディレクトリはその prompt と precheck の原本で、Orca 側を更新するときはここを編集してから反映する。

| automation | id | prompt | precheck |
| --- | --- | --- | --- |
| clawbar issue coordinator | `2fc98fc3-38cb-4e32-92b6-cbb10b39272d` | `issue-coordinator.md` | `issue-coordinator.precheck.sh` |
| clawbar PR reviewer | `bdfdc4fd-3325-4fc9-9038-da99beba7a01` | `pr-reviewer.md` | `pr-reviewer.precheck.sh` |

両方とも 10 分おき（`*/10 * * * *`、Asia/Tokyo）に、既存 workspace `/home/yasuhito/Work/clawbar` で agent `pi` を起動する。precheck の終了コードが 0 のときだけ prompt が実行され、それ以外は skip として記録される。

## 反映

```bash
orca-ide automations edit <id> --prompt "$(cat docs/agents/automations/issue-coordinator.md)" --json
orca-ide automations edit <id> --precheck "$(cat docs/agents/automations/issue-coordinator.precheck.sh)" --precheck-timeout 60 --json
```

## 有効化と停止

```bash
orca-ide automations edit <id> --enabled --json
orca-ide automations edit <id> --disabled --json
orca-ide automations runs --id <id> --json
```

## 動かすための前提

- `main` に `scripts/check` と `.github/workflows/ci.yml` が入っていること。worker worktree は `origin/main` から作られ、PR reviewer は CI checks が 1 件以上成功していないとマージしない。
- 自動実装に渡す issue には `ready-for-agent` と `agent:implement` の両方を付け、本文に `## 実装内容` / `## 受け入れ基準` / `## 対象外` を書く。
- `.pi/extensions/clawbar-orca-role-name.ts` が pi の session 名を役割ごとに付ける。
