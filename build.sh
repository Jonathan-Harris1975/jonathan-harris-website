#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

python3 scripts/check_requirements_lock.py
python3 scripts/check_hash_fail_closed.py

if ! python3 - <<'PYDEP'
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import re

for raw_line in Path("requirements.txt").read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#") or line.startswith("--hash="):
        continue
    clean = line[:-1].rstrip() if line.endswith("\\") else line
    match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^\s\\]+)", clean)
    if not match:
        raise SystemExit(f"Production lock contains an unsupported requirement line: {line}")
    package, expected = match.group(1), match.group(2)
    try:
        installed = version(package)
    except PackageNotFoundError:
        raise SystemExit(1)
    if installed != expected:
        raise SystemExit(1)
PYDEP
then
  python3 -m pip install --disable-pip-version-check --quiet --require-hashes -r requirements.txt
fi
python3 -m pip check

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
python3 scripts/scan_secrets.py
python3 -m unittest scripts.test_pdf_pipeline
node --test workers/agent-readiness/test.mjs
node --test scripts/agent-readiness-pages.test.mjs
node --test scripts/cognipal-rate-limit.test.mjs
# Publish a commit-specific marker so the post-deploy workflow can distinguish
# the new Pages release from an older deployment whose crawler files are unchanged.
python3 scripts/write_release_marker.py
python3 scripts/deployment_ci.py "$@"
python3 scripts/check_repository_hygiene.py
