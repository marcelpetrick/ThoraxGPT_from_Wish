# scripts/

Small, documented helpers. Every script prints its usage from its header comment
(`sed -n '4,20p' scripts/<name>`), runs from any directory, and fails fast (`set -euo pipefail`).

| Script | Purpose | Usage |
|---|---|---|
| `bump_version.sh` | Bump the semver in `src/thoraxbench/__init__.py` | `scripts/bump_version.sh patch\|minor\|major` |
| `commit.sh` | The only way to commit: bump, run `localPipeline.sh`, commit, push | `scripts/commit.sh [--minor] [--fast] [--staged] [--no-push] "feat(x): msg"` |
| `land_branch.sh` | Land a worker branch onto `main` one green commit at a time | `scripts/land_branch.sh [--full] <branch>` |
| `check_headers.sh` | Pipeline stage: SPDX GPL-3.0-or-later header in all sources | `scripts/check_headers.sh` |
| `move_ollama_models_to_home.sh` | One-time root fix: move the system Ollama model store from `/` to `/home` via `OLLAMA_MODELS` | `sudo scripts/move_ollama_models_to_home.sh [TARGET]` |
| `check_no_medical_data.sh` | Pipeline stage: data-policy gate (no DICOM/NIfTI/weights/secrets in git) | `scripts/check_no_medical_data.sh` |
