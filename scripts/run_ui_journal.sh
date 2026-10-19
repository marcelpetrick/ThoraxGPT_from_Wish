#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
# Start the local UI as a user service. No sudo, downloads or boot-time enablement.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
port="${1:-8000}"
if [[ ! "$port" =~ ^[0-9]{4,5}$ ]] || (( 10#$port < 1024 || 10#$port > 65535 )); then
    echo 'Use a port between 1024 and 65535.' >&2
    exit 2
fi
uv_bin="$(command -v uv)"
args=(--user --unit=thoraxbench-local --collect
    --description='ThoraxBench Local research UI'
    --working-directory="$ROOT_DIR"
    --property=StandardOutput=journal --property=StandardError=journal)
if [[ -n "${THORAXBENCH_DATA_DIR:-}" ]]; then
    args+=("--setenv=THORAXBENCH_DATA_DIR=$THORAXBENCH_DATA_DIR")
fi
systemd-run "${args[@]}" "$uv_bin" run --no-sync thoraxbench serve --port "$port"
echo 'Follow: journalctl --user -u thoraxbench-local -f'
echo 'Stop:   systemctl --user stop thoraxbench-local'
