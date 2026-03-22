#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

python3 -m pip install --disable-pip-version-check --quiet -r requirements.txt
python3 scripts/deployment_ci.py
