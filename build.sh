#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

if ! python3 - <<'PYDEP'
import openpyxl
raise SystemExit(0 if openpyxl.__version__ == "3.1.5" else 1)
PYDEP
then
  python3 -m pip install --disable-pip-version-check --quiet -r requirements.txt
fi

DEFAULT_WORKBOOK="$REPO_ROOT/jonathan-harris-site-url-inventory-remediated-release-ready.xlsm"
if [[ -z "${EBOOK_WORKBOOK_PATH:-}" && -f "$DEFAULT_WORKBOOK" ]]; then
  export EBOOK_WORKBOOK_PATH="$DEFAULT_WORKBOOK"
fi

# Podcast episodes, RSS-derived episode lists, and transcript assets are governed
# outside this static website repository. The podcast page uses the embedded
# player for previous episodes, so Pages builds must not collect podcast data.
if command -v node >/dev/null 2>&1; then
  node scripts/generate-blog-from-rss.mjs || echo "WARN: Blog RSS snapshot sync skipped; continuing with the committed fallback."
fi

python3 scripts/check_health_contract.py
python3 scripts/deployment_ci.py "$@"
