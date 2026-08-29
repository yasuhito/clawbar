最初に共通エージェント規約を読む。環境変数 AGENT_KIT_AGENTS が指すファイル、$HOME/Work/agent-kit/AGENTS.MD、../agent-kit/AGENTS.MD の順に存在確認し、最初に見つかったものを読む。なければスキップする。

## Agent skills

### Issue tracker

課題は GitHub Issues で管理する。外部 Pull request は triage 対象にしない。詳細は `docs/agents/issue-tracker.md` を参照する。

### Triage labels

Matt 系スキルの標準 triage 役割は、同名の GitHub label に対応させる。詳細は `docs/agents/triage-labels.md` を参照する。

### Domain docs

このリポジトリは single-context として扱い、ルートの `CONTEXT.md` と `docs/adr/` を使う。詳細は `docs/agents/domain.md` を参照する。

## GitHub issue 規則

- GitHub issue を作成するとき、タイトルは日本語にする。
- 自動実装に渡す issue は、本文に実装契約を書く。`## 実装内容`、`## 受け入れ基準`、`## 対象外` の 3 節を必ず置く。
- 親子関係や依存関係は、本文ではなく GitHub の Relationships metadata（sub-issue、blocked by）に入れる。

## 検証規則

- commit や push の前には、全体チェック `scripts/check` を最新状態で通す。
- 部分的なテストや前回の成功結果ではなく、その時点の作業木に対する最新の実行結果を確認する。

## 自動化ループ

- Orca automation `clawbar issue coordinator` が `ready-for-agent` と `agent:implement` の両方を持つ issue を worker に渡し、PR を作る。
- Orca automation `clawbar PR reviewer` が `agent:review` の PR をレビューし、ゲートを通過した場合だけマージする。
- 自動化に渡したくない issue には `agent:implement` を付けない。`agent:blocked` が付いた issue / PR は人間が原因を確認するまで自動処理されない。
