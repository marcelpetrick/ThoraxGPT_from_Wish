# Open a local DICOM folder

Research use only. ThoraxBench Local is a self-made experimental tool. Outputs may be
incorrect, incomplete or misleading. They are not professional medical advice and must
not inform diagnosis or treatment decisions.

## Procedure

Prerequisites: the local server is running on this computer. Use an existing DICOM CT
study you are permitted to process. Keep the original folder in place. No acquisition,
model download, copy or inference starts when you open a folder.

1. Open **Analyze one study**.
2. Find **Open local DICOM folder** under **Choose a study**.
3. Drop an absolute folder path or a local `file:///` folder link into the folder area.
4. Wait for the automatically queued folder job to complete.
5. Confirm the dataset changes to **Local**.
6. Wait for the selected image in **Study viewer**.
7. Select a model when you are ready to run an analysis.

You can paste the absolute path and select **Open folder** instead. **Browse folders**
opens an in-app directory picker on the server computer. Navigate to the study folder,
then select **Open selected folder**. Existing
indexed dataset/study selection remains available.

**Checkpoint:** the opened study is selected, its slice count appears and a source slice
is visible. Opening does not start a model. Local registrations exist only for this server
session; restarting the server clears them. Source files remain in their original folder.
**Recovery:** choose the folder containing the DICOM CT series, not a JPG/PNG image or
archive. If the folder is unavailable or contains no eligible CT series, correct the path
and retry. A sealed/development access failure must not be bypassed by copying files.

## Browser limits

A browser may hide the absolute path when you drop a real directory. In that case the
interface explains the fallback: paste the path or use **Browse folders**. It does not
guess an absolute path from a folder name, upload file bytes or traverse browser file
handles. A relative path from a directory picker is not a local absolute filesystem path.
See MDN's [relative-path definition](https://developer.mozilla.org/en-US/docs/Web/API/File/webkitRelativePath).
Local file links accept only the local machine; remote file hosts and web URLs are refused.

## Access and queue behavior

Folder checking/loading uses the same sequential worker as inference and model pulls.
Queued jobs can be cancelled. Running cancellation is cooperative at stage boundaries;
a DICOM loading call may finish before cancellation takes effect. Failed or cancelled
opens remain visible. A successful registration is not an analysis or an accuracy result.

The CLI study-input guard checks paths and DICOM header identities before pixels load.
Registered raw inputs require their frozen development split. Sealed paths, symlink
aliases and copied sealed patient identities remain refused. Browsing hides inaccessible
or sealed folders and does not load images. Registered folders are rechecked when opened.
At most 16 local registrations are held in memory. No absolute input path is persisted in
browser storage or job snapshots. Explicit directory browsing displays the selected path
locally; it is not an anonymization feature. Other privacy limitations remain in
[SECURITY.md](../SECURITY.md).

## Read warnings and failures

Opening a folder does not prove that every scanned file belongs to the selected CT series.
The interface separates files scanned, readable headers, unreadable headers and non-DICOM
files. These counts are not the selected slice count. Missing or unusual file extensions
are supported; changing an extension does not repair malformed content.

Wait until the current viewer image loads and input QC permits analysis. Run remains
unavailable while loading or after an unusable input. A failed folder open must not silently
run the previous study. Review warnings before choosing a model.

Select **Details** for a warning or failed job. The trace records the stage, error category,
exception classes, aggregate counts and software identity. Download the diagnostic JSON
when reporting a problem. It excludes input paths, filenames, raw exception messages and
header values. Diagnostics and local registrations last only for the server session.
