# Worktree cleanup — 2026-10-19

The user requested review and cleanup of leftover Git changes. Four historical worktrees
had uncommitted changes. Their tracked diffs and untracked files were preserved in named
local Git recovery stashes before cleaning those worktrees. No old stash, branch, worktree,
ignored data or result was deleted. Stash hashes are stable; numeric stash indices change.
The two pre-existing stashes are retained.

| Worktree | Classification | Recovery stash |
|---|---|---|
| `.claude/worktrees/agent-a2713de6be2350cab` | p6-integrated-with-later-main-fixes | `d07d091e5fefd7003e008cc1664e2f50d1a231d8` |
| `.claude/worktrees/agent-a8afbe19832769108` | privacy-partly-integrated-retain-ad-hoc-hmac-proposal | `0f1e8d2a3bed65f843fc53b54c8c6c2db6d73588` |
| `.pipeline/calibration-port` | calibration-source-identical-to-main | `46f7c9f6d00510a6b5df62e0ed2fcf9dc2d94b98` |
| `.pipeline/docs-commit` | historical-handover-superseded | `176ec65ca8c38b9ec728fbc0f6ec79a719902984` |

The video-framing worker's two changed files were copied byte for byte into the main
media change, then preserved in recovery stash `9e236e569eb606793a592761ae4fd9e9426b2a6b`. Its worktree is clean too.
Synthetic decoded-frame evidence remains locally under
`.pipeline/recovery-20261019/framing-corner-verification.jsonl`.

Calibration source/configuration/tests match main byte for byte. P6 configuration and
integration tests are integrated; main also contains the later binary-answer contradiction
check and token diagnostics. The historical handover is superseded by current AGENTS/plan.
An independent read-only review checked the older privacy/docs work against current main.
Header-redaction/cache handling and stronger provenance hashes are integrated.

## Preserved follow-up: ad hoc identifier pseudonyms

The older privacy patch contains one additional behavior: HMAC pseudonyms for ad hoc
patient/case identifiers, with a local salt and synthetic tests. Current main preserves
these identifiers and explicitly documents that limitation in SECURITY.md. Do not merge
the obsolete whole patch. Port this behavior separately against current identifier/split
contracts, with review of salt persistence, permissions, deterministic keys and provenance.
This remains an open proposal, not a feature implemented by the media change.

## Recovery

Run from the repository root. Inspect a recovery stash before applying it:

```bash
git stash show --stat --include-untracked <STASH_HASH>
```

Use the table's hash. Apply only in an isolated worktree on its recorded historical base,
then review against main. Never blindly apply an old patch to main. Local copies of the
original binary diffs, base hashes and status inventory remain under ignored
`.pipeline/recovery-20261019/`. Each preserved tracked diff was checked byte for byte
against the stash; its untracked-file list was also checked. Stashes are local recovery
objects and are not pushed to GitHub.

**Checkpoint:** historical worktrees have clean `git status --short`. Current authorized
work may still be in progress in main or a dedicated active worker worktree.
**Recovery:** retain stashes until their contents have been deliberately accepted or retired.
