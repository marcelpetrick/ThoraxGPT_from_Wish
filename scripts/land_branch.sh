#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
#
# land_branch.sh — land a worker branch onto main, one green commit at a time.
#
# Each commit of <branch> that is not on main is cherry-picked (without committing) and
# committed through scripts/commit.sh --staged, so it gets its own version bump and must
# pass the pipeline. If a commit is not green on its own (it depends on a later commit),
# the next commit is folded into it and the gate is retried with the combined message
# ("feat(a): x; feat(b): y"). Nothing is ever force-pushed.
#
# Usage: scripts/land_branch.sh [--full] <branch>     (--full runs the full pipeline per commit)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
mode=(--fast)
if [[ "${1:-}" == "--full" ]]; then mode=(); shift; fi
branch="${1:?branch required}"
mkdir -p .pipeline
[[ -z "$(git status --porcelain)" ]] || { echo "working tree not clean" >&2; exit 1; }
mapfile -t commits < <(git rev-list --reverse "main..${branch}")
pending_msg=""
for c in "${commits[@]}"; do
    subject=$(git log -1 --format=%s "$c")
    git cherry-pick -n "$c" || { echo "conflict in $c ($subject); resolve, then rerun" >&2; exit 1; }
    git checkout HEAD -- src/thoraxbench/__init__.py 2>/dev/null || true
    msg="${pending_msg:+${pending_msg}; }${subject}"
    if scripts/commit.sh "${mode[@]}" --staged "$msg" >.pipeline/land_branch.log 2>&1; then
        echo "landed: $msg"
        pending_msg=""
    else
        echo "not green alone, folding into next: $subject"
        pending_msg="$msg"
    fi
done
if [[ -n "$pending_msg" ]]; then
    echo "remaining staged changes are not green: $pending_msg (see .pipeline/land_branch.log)" >&2
    exit 1
fi
