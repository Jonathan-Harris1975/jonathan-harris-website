#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

if ! python3 - <<'PYDEP'
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

requirements = Path("requirements.txt").read_text(encoding="utf-8").splitlines()
for raw_line in requirements:
    line = raw_line.split("#", 1)[0].strip()
    if not line:
        continue
    if "==" not in line:
        raise SystemExit(f"Production requirement must be exactly pinned: {line}")
    package, expected = (part.strip() for part in line.split("==", 1))
    try:
        installed = version(package)
    except PackageNotFoundError:
        raise SystemExit(1)
    if installed != expected:
        raise SystemExit(1)
PYDEP
then
  python3 -m pip install --disable-pip-version-check --quiet -r requirements.txt
fi

DEFAULT_WORKBOOK="$REPO_ROOT/jonathan-harris-site-url-inventory-remediated-release-ready.xlsx"
if [[ -z "${EBOOK_WORKBOOK_PATH:-}" && -f "$DEFAULT_WORKBOOK" ]]; then
  export EBOOK_WORKBOOK_PATH="$DEFAULT_WORKBOOK"
fi

# Podcast episodes, transcripts and weekly blog publications are governed in
# Cloudflare R2/RSS. Pages builds render the website shell and runtime routes
# only; they must not generate or validate committed content snapshots.
if [[ -n "${AMAZON_BOOK_SIGNALS_SOURCE:-}" ]]; then
  python3 scripts/refresh_amazon_book_signals.py
fi

python3 scripts/check_health_contract.py
python3 scripts/check_repository_hygiene.py
python3 scripts/check_hive_skills_route_parity.py
node --test workers/agent-readiness/test.mjs
node --test scripts/agent-readiness-pages.test.mjs
node --test scripts/cognipal-rate-limit.test.mjs
# Publish a commit-specific marker so the post-deploy workflow can distinguish
# the new Pages release from an older deployment whose crawler files are unchanged.
python3 scripts/write_release_marker.py
python3 scripts/deployment_ci.py "$@"
python3 scripts/check_repository_hygiene.py
