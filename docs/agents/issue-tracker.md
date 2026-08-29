# Issue tracker: GitHub

このリポジトリの課題は GitHub Issues で管理する。操作には `gh` CLI を使う。

## 対象リポジトリ

- `yasuhito/clawbar`

## 規約

- 課題を作成する: `gh issue create --title "..." --body "..."`
- 課題を読む: `gh issue view <number> --comments`
- 課題を一覧する: `gh issue list --state open --json number,title,body,labels,comments`
- 課題にコメントする: `gh issue comment <number> --body "..."`
- ラベルを付け外しする: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- 課題を閉じる: `gh issue close <number> --comment "..."`

`gh` はリポジトリ内で実行すれば `git remote` から対象リポジトリを推定する。

## Pull request を triage 対象にするか

**外部 Pull request は triage 対象にしない。**

Pull request は通常のレビュー対象として扱い、Issue と同じキューには入れない。

## スキルが「issue tracker に publish する」と言ったとき

GitHub issue を作成する。

## スキルが「relevant ticket を fetch する」と言ったとき

`gh issue view <number> --comments` で GitHub issue を読む。

## 実装契約

自動実装に渡す issue の本文には、次の 3 節を置く。

- `## 実装内容`: 何をどう変えるか
- `## 受け入れ基準`: 検証できる条件のチェックリスト
- `## 対象外`: この issue でやらないこと

## 自動化ループのラベル

| label | 意味 |
| --- | --- |
| `agent:implement` | `ready-for-agent` と併用すると、issue coordinator が worker に渡す |
| `agent:in-progress` | worker が実装中 |
| `agent:waiting-dependency` | 依存 issue の完了待ち。依存がすべて閉じると自動で `agent:implement` に戻る |
| `agent:blocked` | 自動処理を停止。原因を人間が確認するまで再実行しない |
| `agent:review` | PR がレビュー待ち |
| `agent:reviewing` | PR reviewer がレビュー中 |

## GitHub Relationships

親子関係や依存関係は、issue 本文の `Parent` / `Blocked by` セクションではなく GitHub の Relationships metadata に入れる。本文には実装契約を書き、関係 metadata は GitHub UI と GraphQL で確認できる状態にする。

`gh issue edit` には親子関係を直接編集するオプションがないため、`gh api graphql` を使う。

親 issue に子 issue を追加する例:

```bash
gh api graphql \
  -f issueId="$PARENT_ISSUE_ID" \
  -f subIssueId="$CHILD_ISSUE_ID" \
  -F replaceParent=true \
  -f query='mutation($issueId:ID!, $subIssueId:ID!, $replaceParent:Boolean) { addSubIssue(input:{issueId:$issueId, subIssueId:$subIssueId, replaceParent:$replaceParent}) { issue { number } subIssue { number parent { number } } } }'
```

依存関係を追加する例:

```bash
gh api graphql \
  -f issueId="$BLOCKED_ISSUE_ID" \
  -f blockingIssueId="$BLOCKING_ISSUE_ID" \
  -f query='mutation($issueId:ID!, $blockingIssueId:ID!) { addBlockedBy(input:{issueId:$issueId, blockingIssueId:$blockingIssueId}) { issue { number blockedBy(first:10) { nodes { number } } } } }'
```

issue ID は次のように取得する。

```bash
gh api graphql \
  -f owner=yasuhito \
  -f name=clawbar \
  -F number="$ISSUE_NUMBER" \
  -f query='query($owner:String!, $name:String!, $number:Int!) { repository(owner:$owner, name:$name) { issue(number:$number) { id } } }'
```

## 履歴

2026-08-29 まで Beads（`br`）で管理していた。閉じた課題の記録は git 履歴の `.beads/issues.jsonl` に残っている。
