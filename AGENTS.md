## Domain docs

このリポジトリは single-context として扱い、ルートの `CONTEXT.md` と `docs/adr/` を使う。詳細は `docs/agents/domain.md` を参照する。

## 検証規則

- commit や push の前には、全体チェック `scripts/check` を最新状態で通す。
- 部分的なテストや前回の成功結果ではなく、その時点の作業木に対する最新の実行結果を確認する。
