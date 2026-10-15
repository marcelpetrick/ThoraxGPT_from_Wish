#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
#
# bump_version.sh — bump the semantic version stored in src/thoraxbench/__init__.py.
#
# Project rule: every commit bumps `patch`; a major feature bumps `minor`
# (which resets patch to 0); `major` is reserved for breaking protocol changes.
#
# Usage: scripts/bump_version.sh patch|minor|major     (prints the new version)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
file=src/thoraxbench/__init__.py
current=$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$file")
IFS=. read -r major minor patch <<<"$current"
case "${1:-}" in
    patch) patch=$((patch + 1)) ;;
    minor) minor=$((minor + 1)); patch=0 ;;
    major) major=$((major + 1)); minor=0; patch=0 ;;
    *) echo "usage: $0 patch|minor|major" >&2; exit 2 ;;
esac
new="${major}.${minor}.${patch}"
sed -i "s/^__version__ = \".*\"$/__version__ = \"${new}\"/" "$file"
echo "$new"
