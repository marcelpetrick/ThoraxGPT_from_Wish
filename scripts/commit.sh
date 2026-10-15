#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
#
# commit.sh — the one way to commit in this repository.
#
# 1. bumps the version (patch by default, `--minor` for a major feature),
# 2. runs ./localPipeline.sh (full; pass `--fast` to run the fast subset),
# 3. stages everything and commits with the given conventional-commit message,
# 4. pushes to origin (skip with `--no-push`).
#
# Usage: scripts/commit.sh [--minor] [--fast] [--no-push] "feat(scope): message"
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
level=patch; pipeline_args=(); push=true
while [[ $# -gt 1 ]]; do
    case "$1" in
        --minor) level=minor ;;
        --fast) pipeline_args+=(--fast) ;;
        --no-push) push=false ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done
msg="${1:?commit message required}"
if ! [[ "$msg" =~ ^(feat|fix|docs|test|refactor|perf|build|ci|chore|style)(\([a-z0-9_-]+\))?!?:\ .+ ]]; then
    echo "not a conventional commit message: $msg" >&2; exit 2
fi
old_version=$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' src/thoraxbench/__init__.py)
version=$(scripts/bump_version.sh "$level")
if ! ./localPipeline.sh "${pipeline_args[@]}"; then
    sed -i "s/^__version__ = \".*\"$/__version__ = \"${old_version}\"/" src/thoraxbench/__init__.py
    echo "pipeline red — version bump reverted, nothing committed" >&2
    exit 1
fi
git add -A
git commit -q -m "$msg" -m "Version: ${version}"
echo "committed ${version}: $msg"
if [[ "$push" == true ]]; then git push -q origin HEAD; echo "pushed"; fi
