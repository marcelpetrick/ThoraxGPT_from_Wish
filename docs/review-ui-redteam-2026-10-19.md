# UI/UX red-team review — 2026-10-19

Base: `6e1ddb3` (v0.5.1 diagnostics follow-up) · Branch: `worktree-agent-adaee9c50f1832a28`

Scope: the operator path with a local DICOM folder (path, file link and folder browser →
import progress → viewer/QC → detector or baseline run → candidate review → offline HTML),
plus Evaluation, Jobs, EN/DE, light/dark and a 360 px mobile width. The review drove the
real server with a generated phantom folder (one truncated extra file) and mocked folder
jobs. No private source, sealed input or real patient image was opened or captured.

## Ranked findings

1. **HIGH · Stale state · `app.js` `openLocalFolder`/`folderJobFailure`:** after a failed
   or refused folder open, the study selector and the phase/QC/slice badges still showed the
   previous study while the viewer said analysis was blocked. Re-choosing that study in a
   real browser fires no `change` event, so the documented recovery ("explicitly select a
   library study") did not work for it. **Fixed:** a blocked attempt shows a
   *Choose a study…* placeholder and `—` badges; any real study choice unblocks.
2. **HIGH · Missing state · Run button:** Run was silently disabled (no study, image
   loading/failed, blocked folder, limited local QC, unavailable model, model download).
   **Fixed:** a translated `role=status` line under Run names the first blocking reason
   and disappears when Run is enabled.
3. **MEDIUM · Progress placement and accessibility:** import counts appeared under the Run
   button in step 2, far from the folder controls, and the polite live region re-announced
   every poll. **Fixed:** counts sit below the folder notice, the region is `aria-live=off`,
   and the shared announcer reads only each new loading operation.
4. **MEDIUM · Untranslated server text:** the fixed 403 refusal ("Local folder is
   unavailable or not permitted") appeared in English in German mode, in the folder notice
   and the browser dialog. **Fixed:** the known refusal maps to translated EN/DE text that
   names missing, non-folder and protected paths; other details stay escaped text.
5. **MEDIUM · Header-warning wording / informational counter:** the warning read like a
   partial failure and the diagnostics dialog called a succeeded import a failed job.
   `private_values_raw` (vendor-private values kept as raw bytes) had no label and was
   dropped from exported diagnostics. **Fixed:** "Opened with a warning: N file(s) with
   unreadable DICOM headers were skipped"; the dialog prefixes *Warning only; the import
   succeeded*; the download tip covers failures and warnings. The raw-value counter is
   shown as *(informational)*, exported via `DISCOVERY_COUNTERS`, and never adds a warning.
6. **MEDIUM · Misleading wording (import ≠ result):** import jobs offered *Open result* and
   a `—` model column in the job notice. **Fixed:** *Open study*, no model placeholder, and
   the notice adds "study opened; not a model result". The opened notice states that
   opening a folder is not a model result or an accuracy check.
7. **LOW · Accessibility of errors:** a refused or invalid path gave no field-level error.
   **Fixed:** the path input gets `aria-invalid`/`aria-errormessage`, receives focus and
   keeps the text for correction; typing clears the invalid state.
8. **LOW · Inconsistent study label:** result and comparison context showed
   `local / <full session UUID>` while the selector showed *Local study 1a2b3c4d*.
   **Fixed:** context uses the same translated short label.

## Follow-up fixes (2026-10-20)

9. **Announcer language:** the visually hidden job announcer kept its last English sentence
   after a switch to German. **Fixed:** the last announcement is rebuilt in the new language.
10. **Inert download links:** disabled links stayed in the tab order. **Fixed:** they get
    `tabindex="-1"` until a result enables them, and a visible hint says when downloads
    become available.
11. **English server errors:** `job.error` without a diagnostic code stayed English.
    **Fixed:** known messages are translated; other server text gets a translated lead and is
    marked as the English server detail.
12. **Mobile job notice:** the fixed bottom notice wrapped to several lines and the page used a
    guessed 135 px padding. **Fixed:** one truncated line (full text in its title) and the
    page is padded by the notice's measured height, so the end of the page stays reachable.
13. **Jobs table at 360 px:** it scrolled horizontally. **Fixed:** below 640 px each job is a
    stacked card with column names as labels.

Evaluation, About and the offline HTML report showed no new wording or layout issue.
Contrast tokens checked for body, muted, warning and accent text exceed 4.5:1.

## Verification

New `tests/e2e/test_ui_redteam.py` covers findings 1, 2, 4, 6 and 7 in EN/DE;
`tests/e2e/test_ui_leftovers.py` covers findings 9–13.
`test_folder_import_progress.py` asserts finding 3, `test_job_diagnostics_ui.py` findings 5
and 6, and the real-folder workflow test asserts finding 8 offline. Integration tests cover
the exported counter whitelist and the page landmarks. Passing tests establish software
behavior only, not model accuracy or diagnostic usefulness.
