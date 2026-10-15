#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
#
# check_headers.sh — verify that every tracked or new Python/shell source file carries the
# SPDX GPL-3.0-or-later license header in its first five lines.
#
# Usage: scripts/check_headers.sh        (exit 1 and list offenders on failure)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
missing=0
while IFS= read -r f; do
    [[ -f "$f" ]] || continue
    if ! head -n 5 "$f" | grep -q 'SPDX-License-Identifier: GPL-3.0-or-later'; then
        echo "missing license header: $f"
        missing=1
    fi
done < <(git ls-files --cached --others --exclude-standard -- '*.py' '*.sh' 'Dockerfile')
[[ ${missing} -eq 0 ]] && echo "all source files carry the GPL-3.0-or-later SPDX header"
exit "${missing}"
