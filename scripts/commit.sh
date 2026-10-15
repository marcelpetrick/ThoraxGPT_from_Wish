#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
#
# commit.sh — the one way to commit in this repository.
#
# 1. bumps the version (patch by default, `--minor` for a major feature),
# 2. runs ./localPipeline.sh (full; pass `--fast` to run the fast subset),
# 3. commits with the given conventional-commit message — everything by default, or with
#    `--staged` only what is already staged (unstaged/untracked changes are stashed while the
#    pipeline runs, so the gate really tests exactly the committed tree),
# 4. pushes to origin (skip with `--no-push`).
#
# Usage: scripts/commit.sh [--minor] [--fast] [--staged] [--no-push] "feat(scope): message"
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
level=patch; pipeline_args=(); push=true; staged=false
while [[ $# -gt 1 ]]; do
    case "$1" in
        --minor) level=minor ;;
        --fast) pipeline_args+=(--fast) ;;
        --no-push) push=false ;;
        --staged) staged=true ;;
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
stashed=false
if [[ "$staged" == true ]]; then
    git add src/thoraxbench/__init__.py
    if [[ -n "$(git status --porcelain --untracked-files=all | grep -v '^[MADR] ' || true)" ]]; then
        git stash push -q --keep-index --include-untracked -m commit.sh && stashed=true
    fi
fi
restore() { if [[ "$stashed" == true ]]; then git stash pop -q; fi; }
if ! ./localPipeline.sh "${pipeline_args[@]}"; then
    restore
    sed -i "s/^__version__ = \".*\"$/__version__ = \"${old_version}\"/" src/thoraxbench/__init__.py
    if [[ "$staged" == true ]]; then git add src/thoraxbench/__init__.py; fi
    echo "pipeline red — version bump reverted, nothing committed" >&2
    exit 1
fi
if [[ "$staged" == false ]]; then git add -A; fi
git commit -q -m "$msg" -m "Version: ${version}"
restore
echo "committed ${version}: $msg"
if [[ "$push" == true ]]; then git push -q origin HEAD; echo "pushed"; fi
