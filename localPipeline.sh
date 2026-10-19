#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
#
# localPipeline.sh — the single quality gate for ThoraxBench Local.
#
# The GitHub Actions workflow `.github/workflows/local-pipeline.yml` runs this exact
# script, so a green local run means a green CI run.
#
# Stages (in order; the pipeline stops at the first failing stage):
#   sync       uv sync --frozen (Python 3.14 virtualenv from uv.lock)
#   headers    SPDX/GPL license header present in every source file
#   datagate   no medical image data / weights / secrets tracked by git
#   format     ruff format --check
#   lint       ruff check
#   types      mypy --strict on src/
#   tests      pytest (unit + integration + e2e, without `live`) with coverage >= 95 %
#   build      uv build (sdist + wheel)
#   wheel      install the wheel into a clean venv and run `thoraxbench --version`
#   audit      pip-audit against the locked dependency set
#
# Usage:
#   ./localPipeline.sh                 # everything
#   ./localPipeline.sh --fast          # sync, headers, datagate, format, lint, types, tests
#   ./localPipeline.sh --only tests    # one stage (repeatable: --only lint --only types)
#   ./localPipeline.sh --help
#
# Logs of each stage are written to .pipeline/<stage>.log.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT_DIR}"
LOG_DIR="${ROOT_DIR}/.pipeline"
PY="${ROOT_DIR}/.venv/bin/python"
ALL_STAGES=(sync headers datagate format lint types tests build wheel audit)
FAST_STAGES=(sync headers datagate format lint types tests)
SELECTED=()

usage() { sed -n '4,30p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --fast) SELECTED=("${FAST_STAGES[@]}") ;;
        --only) shift; SELECTED+=("$1") ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown option: $1" >&2; usage; exit 2 ;;
    esac
    shift
done
[[ ${#SELECTED[@]} -eq 0 ]] && SELECTED=("${ALL_STAGES[@]}")

mkdir -p "${LOG_DIR}"
declare -a SUMMARY=()

stage_sync()     { uv sync --frozen --all-groups; }
stage_headers()  { "${ROOT_DIR}/scripts/check_headers.sh"; }
stage_datagate() { "${ROOT_DIR}/scripts/check_no_medical_data.sh"; }
stage_format()   { "${PY}" -m ruff format --check .; }
stage_lint()     { "${PY}" -m ruff check .; }
stage_types()    { "${PY}" -m mypy; }
stage_tests() {
    COVERAGE_FILE="${LOG_DIR}/.coverage" "${PY}" -m pytest -m "not live" \
        --cov --cov-report=term-missing \
        --cov-report="html:${LOG_DIR}/htmlcov" --cov-report="xml:${LOG_DIR}/coverage.xml"
}
stage_build() { rm -rf dist && uv build -q; }
stage_wheel() {
    local tmp
    tmp="$(mktemp -d)"
    uv venv -q --python 3.14 "${tmp}/venv"
    uv pip install -q --python "${tmp}/venv/bin/python" dist/*.whl
    "${tmp}/venv/bin/thoraxbench" --version
    rm -rf "${tmp}"
}
stage_audit() {
    uv export --frozen --all-extras --all-groups --no-emit-project -o "${LOG_DIR}/requirements.audit.txt" -q
    "${PY}" -m pip_audit --strict --no-deps --disable-pip --progress-spinner off -r "${LOG_DIR}/requirements.audit.txt"
}

overall=0
for stage in "${SELECTED[@]}"; do
    log="${LOG_DIR}/${stage}.log"
    start=$(date +%s)
    printf '==> %-9s ' "${stage}"
    if "stage_${stage}" >"${log}" 2>&1; then
        SUMMARY+=("PASS  ${stage}  ($(( $(date +%s) - start ))s)")
        echo "PASS"
    else
        SUMMARY+=("FAIL  ${stage}  (see ${log})")
        echo "FAIL"
        tail -n 40 "${log}"
        overall=1
        break
    fi
done

echo
echo "================ localPipeline summary ================"
printf '%s\n' "${SUMMARY[@]}"
[[ ${overall} -eq 0 ]] && echo "RESULT: GREEN" || echo "RESULT: RED"
exit "${overall}"
