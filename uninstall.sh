#!/bin/bash
# Default is a read-only plan. No purge or external/Hermes lifecycle operations.
set -euo pipefail
case "${1:-}" in
    '') mode=--uninstall-plan ;;
    --apply) mode=--uninstall-apply ;;
    --help|-h) echo 'Usage: bash uninstall.sh [--apply]'; exit 0 ;;
    *) echo 'Usage: bash uninstall.sh [--apply]' >&2; exit 1 ;;
esac
[ "$#" -le 1 ] || exit 1
exec bash "$(cd "$(dirname "$0")" && pwd)/deploy.sh" "$mode"
