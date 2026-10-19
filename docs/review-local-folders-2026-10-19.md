# Local-folder release review — 2026-10-19

Base: origin/main @ `688ac0c` · Head before release: `688ac0c`

Committed comparison: 0 files changed, +0 / -0 lines.

The standard `reviewBranch` comparison (`git diff origin/main...HEAD`) is empty because
work takes place directly on main. Two independent reviewers and the lead reviewed the
pending working-tree patch, including new files, to cover the actual release changes.

## Confirmed findings and fixes

1. **MEDIUM · Code · `src/thoraxbench/api/static/app.js`, `importedStudy`:** a delayed
   folder A library response could select A and unblock Run after folder B started.
   Input-intent generations now reject stale continuations. Explicit selection and newer
   attempts also stop following earlier import jobs; server jobs remain in the queue.
2. **MEDIUM · Code · `src/thoraxbench/api/static/app.js`, `filterStudies`:** search alone
   cleared a failed-import block, making the previous study runnable without reselection.
   Search retains the block. Explicit study/dataset selection is the recovery action.
3. **MEDIUM · Code · `src/thoraxbench/api/static/app.js`, `filterStudies`:** unrelated
   search reset slice 5 to the middle slice when its image had not loaded. The existing
   UX-01 acceptance test reproduced this. Unchanged-study reloads now preserve the slice.

4. **MEDIUM · Code · `src/thoraxbench/api/static/app.js`, `refreshStudies`:** an old
   inventory response could replace newly opened B with A and enable A with B's success
   notice. Refresh now checks its captured input generation before updating the library;
   a synthetic delayed-response regression reproduces and prevents this path.

Earlier implementation review also corrected fatal pixel-error classification and cache
invalidation after split-policy changes. No confirmed backend Code or Architecture finding
remains. Header/split guards run before new pixel loads; unchanged cached pixels avoid
header rescans while still checking source and policy identity.

## Verification

Tests use generated phantoms or clearly labelled mocked responses. No private source folder,
sealed patient input or real patient screenshot is needed. New browser regressions exercise
delayed A/B completion, failed B, pending submission, running-import manual reselection,
search after failure, stale image events, retry and local QC blocking. All 39 focused
folder, readiness, diagnostics and existing UX acceptance checks pass. Actual synthetic
extensionless-folder → viewer → analysis → offline HTML and diagnostic downloads are checked.

Release acceptance requires the complete `scripts/commit.sh` gate: locked installation,
license/data checks, formatting, lint, strict typing, full tests with coverage at least 95%,
package build, clean-wheel installation and dependency audit. GitHub Actions repeats the
same gate. Passing these checks establishes software behavior, not model accuracy.

**Verdict:** the confirmed review findings are addressed. Release only with the full gate
passing; preserve explicit model limitations and the sealed holdout.

## Follow-up diagnostics review

The operator helper and live loading/logging follow-up received another independent review.
The following confirmed findings were fixed before release:

- The header helper's default argument errors could echo an unquoted identifying filename.
  Its parser now emits fixed text, verified by a subprocess test with a synthetic secret.
- Optional pixel decoding initially lacked copied-sealed-patient identity validation.
  The helper now shares the single-header policy with the folder guard; synthetic copied
  sealed inputs and known sealed paths are refused before pixel reads. Corrupt or bounded
  incomplete headers cannot enable pixel decoding.
- Default HTTP access logs could retain folder-query paths in the user journal. CLI serving
  now disables access logs while retaining sanitized structured job events.
- Directory traversal counters labelled entries as files. Path/source counters now use
  entries; header/pixel passes use files and QC uses checks.

Nineteen helper tests, eight log/progress tests and the focused integration/browser checks use
synthetic data only. Actual systemd-user journal verification recorded all six operations
for a synthetic import, with private rotating JSON logs. Current journal retention remains
a host setting. No private user image was accessed. The complete local/CI gate remains the
release condition; none of these execution checks establishes diagnostic accuracy.
