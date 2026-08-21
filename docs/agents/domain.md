# Domain Docs

How the engineering skills should consume this repository's domain documentation when exploring the codebase.

## Before exploring, read these

- `CONTEXT.md` at the repository root.
- Relevant ADRs under `docs/adr/`.

If either location does not exist, proceed silently. Domain-modeling workflows create these files when terminology or durable decisions are resolved.

## File structure

This repository uses a single-context layout:

```text
/
├── CONTEXT.md
├── docs/adr/
└── src/
```

## Use the glossary's vocabulary

Use terms as defined in `CONTEXT.md` in issue titles, specifications, hypotheses, tests, and implementation. If a needed concept is absent, reconsider whether new language is necessary or record the gap for domain modeling.

## Flag ADR conflicts

Surface any conflict with an existing ADR explicitly instead of silently overriding the decision.
