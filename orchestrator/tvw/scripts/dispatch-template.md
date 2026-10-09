# Dispatch body template (R10a, 2026-08-19)

Every dispatch body follows this envelope. The frontmatter (id/date/lanes/sha256) is
added by `dispatch.sh send`; this template is the BODY. Send with
`--predict h,sessions,p` — calibration stats stay at n=0 without it.

```markdown
## Objective
One sentence: what done looks like.

## Scope
What is in; what is explicitly out. Which repo/branch to land on.

## Acceptance criteria
Deterministic checks, one per line. The ack must show each one ran.

## Evidence required
What the ack's evidence receipt must contain: changed paths, commit ids,
test/command output, unresolved limits.

## Dependencies
Data, prior dispatches, endpoints, or approvals this work waits on. State the
deployment prior explicitly (e.g. fixed bias-field direction) — silence defaults
to the general case and defeats architectures that exploit the prior.

## Source revision
Repo + commit/branch the request was written against.

## Reply destination
Usually: ack note + TVW picks it up at next session. Name anything else.
```

Ack format: `dispatch.sh ack <id> --actual h,sessions,outcome "<evidence receipt>"`.
The receipt is a mini post-mortem: what changed (paths + commits), what checks ran
with results, what premises of the dispatch turned out wrong, unresolved limits.
