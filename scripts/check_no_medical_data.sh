#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
#
# check_no_medical_data.sh — data-policy gate (Vision §7, §23, §29, §30).
#
# Fails when git tracks (or is about to track) medical image data, model weights, large
# binaries or secrets. Files under tests/fixtures are allowed only if they are tiny
# synthetic phantoms (< 200 KB).
#
# Usage: scripts/check_no_medical_data.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
bad=0
pattern='\.(dcm|DCM|nii|nii\.gz|nrrd|mha|mhd|npz|npy|gguf|safetensors|pt|pth|ckpt|zip|tar|tgz)$|(^|/)\.env$|(^|/)data/'
while IFS= read -r f; do
    [[ -f "$f" ]] || continue
    if [[ "$f" =~ ${pattern} ]]; then
        echo "forbidden file type tracked: $f"; bad=1
    fi
    size=$(stat -c %s "$f")
    if (( size > 2000000 )) && [[ "$f" != uv.lock ]]; then
        echo "file larger than 2 MB tracked: $f (${size} bytes)"; bad=1
    fi
    if [[ "$f" == tests/fixtures/* ]] && (( size > 200000 )); then
        echo "test fixture larger than 200 KB: $f"; bad=1
    fi
done < <(git ls-files --cached --others --exclude-standard)
if git ls-files --cached --others --exclude-standard -z | xargs -0 -r grep -l -I -E '(hf_[A-Za-z0-9]{30,}|ghp_[A-Za-z0-9]{30,}|gho_[A-Za-z0-9]{30,})' 2>/dev/null; then
    echo "possible secret/token found in the files above"; bad=1
fi
[[ ${bad} -eq 0 ]] && echo "data-policy gate passed: no medical data, weights or secrets tracked"
exit "${bad}"
