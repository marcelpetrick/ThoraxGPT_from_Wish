# Security policy

Research use only. This self-made tool is not professional medical advice. Its findings
may be incorrect, incomplete or misleading. Do not use them for diagnosis or treatment.

## Scope

ThoraxBench Local is a local research tool for one workstation. It is not a clinical
system, a hosted service or a medical device. It has no user accounts and no remote
access. This policy covers the source code in this repository and the local web
interface started by `uv run thoraxbench serve`.

Out of scope: the security of Ollama, local model services, model weights, the operating
system and the data providers. Report problems in those components to their maintainers.

## Supported versions

Only the latest commit on `main` is supported. Fixes are not backported to older
versions or tags. The installed version prints with `uv run thoraxbench --version`.

## Implemented controls

### Loopback-only web interface

1. `thoraxbench serve` binds to `127.0.0.1` only and disables proxy headers
   (`src/thoraxbench/cli/main.py`). The port option accepts 1024–65535.
2. The app accepts only loopback `Host` headers (`localhost` or a loopback IP address).
   See `_local_host` in `src/thoraxbench/api/app.py`.

### Loopback-only inference

1. Every model client passes `require_local_endpoint`
   (`src/thoraxbench/adapters/factory.py`).
2. The guard accepts only `http` or `https` URLs whose host is `localhost` or a loopback
   IP address.
3. The guard rejects URLs with credentials, a query, a fragment, whitespace or port 0.
4. The HTTP client ignores environment proxies (`trust_env=False`) and does not follow
   redirects. Local medical input cannot be forwarded to another host this way.
5. Tests: `tests/unit/test_local_endpoints.py`.

Endpoints come from `THORAXBENCH_OLLAMA_URL` (default `http://localhost:11434`) and the
`THORAXBENCH_*_URL` service variables in `src/thoraxbench/config.py`. A non-loopback
value makes the model unavailable. It does not open a remote connection.

LAN inference on a second machine is **planned** only. The proposed design is in
[`docs/lan-runner.md`](docs/lan-runner.md). Do not weaken the loopback guard to try it.

### Network traffic and telemetry

* The code contains no telemetry, analytics or crash reporting.
* The web interface loads only local templates, styles and scripts. It uses no CDN.
* The code makes no cloud inference call.
* The only internet traffic started from the interface is an explicit model download.
  The user acknowledges the model terms first. The local Ollama server then pulls the
  configured tag from its registry. Study images are not sent.
* `thoraxbench acquire` downloads approved TCIA collections from the public NBIA REST API
  (`src/thoraxbench/acquisition/`). It refuses a dataset whose registry status is not
  `approved*`, a series under another license or collection, new patients after a split,
  and a plan that exceeds the data budget. It sends no study data.

### Data and secrets in Git

* `.gitignore` excludes `data/`, DICOM, NIfTI and other volume formats, model weights,
  `.env` and `*.token` files.
* `scripts/check_no_medical_data.sh` fails the pipeline when Git tracks forbidden file
  types, files under `data/`, large files, or strings that look like Hugging Face or
  GitHub tokens. See [`DATA_POLICY.md`](DATA_POLICY.md) for the full rule set.
* Self-contained HTML reports must stay inside `data/results/`. `require_results_path`
  in `src/thoraxbench/reports/html_report.py` resolves symlinks before the check.
* Model text in HTML reports is escaped.

### Privacy audit and redaction

* `thoraxbench privacy audit DIR` checks DICOM headers against a subset of the PS3.15
  Basic Profile. It prints tag keywords and counts, never values
  (`src/thoraxbench/privacy.py`).
* `analyze` results, reports, HTML exports, web API responses and CLI errors redact
  absolute paths. See [`docs/architecture.md`](docs/architecture.md#9-privacy-checks-vision-29).

### Sealed holdout

The sealed 20 % holdout is a research-integrity control, not an access-control boundary
against a local administrator. See [`DATA_POLICY.md`](DATA_POLICY.md#4-sealed-holdout).

## Known gaps

These items are not implemented (Vision §29,
[`docs/vision_traceability.md`](docs/vision_traceability.md)):

* pixel-level detection of burned-in text (the header audit does not inspect pixels);
* a complete `data/` write quota: only `acquire` enforces the disk budget, for its own
  downloads;
* redaction of `data/cache/` and `data/index/` files, which keep DICOM `PatientID` values
  under ignored `data/`.

## Report a vulnerability

Prerequisites: a description of the problem, the affected commit and steps to reproduce
it. Use synthetic data only. Never attach patient images, DICOM files or tokens.

1. Open a private security advisory on GitHub:
   <https://github.com/marcelpetrick/ThoraxGPT_from_Wish/security/advisories/new>.
2. If you cannot use GitHub, send an e-mail to `mail@marcelpetrick.it`.
3. Do not open a public issue for a vulnerability.

**Checkpoint:** you receive an acknowledgement. This is a single-maintainer project;
response times are best effort and not guaranteed.

**Recovery:** if the advisory form is unavailable, use the e-mail address.

Examples of relevant reports: a bypass of the loopback guard, a path that lets a report
or download escape `data/results/`, a way to read sealed cases without a freeze record,
or a committed file that contains medical data or a secret.
