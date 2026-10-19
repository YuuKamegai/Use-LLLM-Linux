#!/usr/bin/env bash
set -euo pipefail
root="$HOME/Use-LLLM-Linux"
exec "$root/current/.venv/bin/python" "$root/current/tools/linux/deploy.py" update "$@"
