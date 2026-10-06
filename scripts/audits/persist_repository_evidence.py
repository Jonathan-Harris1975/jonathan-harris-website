#!/usr/bin/env python3
"""Persist repository CI/DAST/Council evidence to the existing R2 archive."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from scripts.audits.common import build_r2_client


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", required=True, choices=("dast", "council"))
    parser.add_argument("--repository", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--run-attempt", required=True, type=int)
    parser.add_argument("--status", required=True)
    parser.add_argument("--attach", action="append", default=[])
    args = parser.parse_args()

    bucket = "hive-repositories"
    prefix = (
        f"repository-evidence/{args.repository}/{args.kind}/{args.sha}/"
        f"run-{args.run_id}-attempt-{args.run_attempt}"
    )
    evidence = {
        "schema": "repository-evidence/v1",
        "kind": args.kind,
        "repository": args.repository,
        "default_branch_sha": args.sha,
        "workflow_run_id": args.run_id,
        "workflow_run_attempt": args.run_attempt,
        "status": args.status,
    }

    client = build_r2_client()
    client.put_object(
        Bucket=bucket,
        Key=f"{prefix}/evidence.json",
        Body=(json.dumps(evidence, indent=2, sort_keys=True) + "\n").encode(),
        ContentType="application/json",
    )
    for raw in args.attach:
        path = Path(raw)
        if path.is_file():
            client.upload_file(str(path), bucket, f"{prefix}/{path.name}")

    print(f"Persisted evidence to r2://{bucket}/{prefix}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
