#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
#
# move_ollama_models_to_home.sh — relocate the system Ollama service's model store from the
# root partition (/usr/share/ollama/.ollama/models) to the /home partition, using the
# OLLAMA_MODELS environment override of the systemd unit. Run once, as root:
#
#   sudo scripts/move_ollama_models_to_home.sh [TARGET]      (default TARGET=/home/ollama/models)
#
# Steps: stop ollama → rsync models to TARGET (owned by ollama:ollama) → add
# Environment="OLLAMA_MODELS=TARGET" to /etc/systemd/system/ollama.service.d/override.conf →
# daemon-reload + start → verify /api/tags → only then delete the old store on /.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "run with sudo" >&2; exit 1; }
target="${1:-/home/ollama/models}"
old=/usr/share/ollama/.ollama/models
override=/etc/systemd/system/ollama.service.d/override.conf
mkdir -p "$target"
systemctl stop ollama
rsync -a --remove-source-files --exclude '*-partial' "$old/" "$target/"
chown -R ollama:ollama "$(dirname "$target")"
mkdir -p "$(dirname "$override")"
touch "$override"
grep -q '^\[Service\]' "$override" || echo '[Service]' >> "$override"
sed -i '/OLLAMA_MODELS=/d' "$override"
sed -i "/^\[Service\]/a Environment=\"OLLAMA_MODELS=${target}\"" "$override"
systemctl daemon-reload
systemctl start ollama
for _ in $(seq 1 30); do curl -sf http://127.0.0.1:11434/api/tags >/dev/null && break; sleep 1; done
curl -sf http://127.0.0.1:11434/api/tags | grep -o '"name":"[^"]*"' || { echo "ollama did not come back" >&2; exit 1; }
find "$old" -name '*-partial' -delete 2>/dev/null || true
find "$old" -type d -empty -delete 2>/dev/null || true
echo "models now in ${target}; override:"; cat "$override"; df -h / /home
