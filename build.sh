#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

python3 -m pip install --disable-pip-version-check --quiet -r requirements.txt

DEFAULT_WORKBOOK="$REPO_ROOT/jonathan-harris-site-url-inventory-remediated-release-ready.xlsm"
if [[ -z "${EBOOK_WORKBOOK_PATH:-}" && -f "$DEFAULT_WORKBOOK" ]]; then
  export EBOOK_WORKBOOK_PATH="$DEFAULT_WORKBOOK"
fi

python3 scripts/sync_podcast_episodes.py
python3 scripts/deployment_ci.py "$@"
