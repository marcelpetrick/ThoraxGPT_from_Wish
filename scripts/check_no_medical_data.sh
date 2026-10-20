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
    # User-approved public demo cuts only; pin reviewed bytes, not a general media exemption.
    approved_video_sha256=''
    case "$f" in
        media/pilot-A.mp4) approved_video_sha256='27c25da7cad41092f62a09c9a8e0d05022b22526ecaa90d2c4a2cebf80224bcd' ;;
        media/pilot-B.mp4) approved_video_sha256='a8fd0a99f58da65930fc34ae6c038992c0d52c9aea094d73fa5584001023f1f1' ;;
        media/promo-16x9.mp4) approved_video_sha256='c0d725d2f53be048b10d3e2349fcbd8062791b763af3f62c5c6ac32822482735' ;;
    esac
    if [[ -n "$approved_video_sha256" ]]; then
        actual_video_sha256=$(sha256sum "$f")
        if [[ "${actual_video_sha256%% *}" != "$approved_video_sha256" ]]; then
            echo "public demo video differs from reviewed bytes: $f"; bad=1
        fi
    fi
    size=$(stat -c %s "$f")
    if (( size > 2000000 )) && [[ "$f" != uv.lock ]] && [[ -z "$approved_video_sha256" ]]; then
        echo "file larger than 2 MB tracked: $f (${size} bytes)"; bad=1
    fi
    if [[ "$f" == tests/fixtures/* ]] && (( size > 200000 )); then
        echo "test fixture larger than 200 KB: $f"; bad=1
    fi
done < <(git ls-files --cached --others --exclude-standard)
if git ls-files --cached --others --exclude-standard -z | xargs -0 -r grep -l -I -E '(hf_[A-Za-z0-9]{30,}|ghp_[A-Za-z0-9]{30,}|gho_[A-Za-z0-9]{30,})' 2>/dev/null; then
    echo "possible secret/token found in the files above"; bad=1
fi
[[ ${bad} -eq 0 ]] && echo "data-policy gate passed: no forbidden file types, unapproved oversized binaries or secrets tracked"
exit "${bad}"
