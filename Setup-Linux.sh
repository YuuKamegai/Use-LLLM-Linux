#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if ! command -v uv >/dev/null 2>&1; then
  printf '%s\n' 'uv is required. See docs/linux/README.md.' >&2
  exit 2
fi
exec "$(command -v uv)" run --no-project --python 3.12.13 python "$root/tools/linux/deploy.py" install "${1:-$root}"
