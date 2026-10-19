#!/usr/bin/env bash
set -euo pipefail
root="$HOME/Use-LLLM-Linux"
exec "$root/current/.venv/bin/python" -m use_lllm.linux.launcher "${@:-start}"
