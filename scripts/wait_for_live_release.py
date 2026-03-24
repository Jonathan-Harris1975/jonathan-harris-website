#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.check_crawlers import print_live_summary, run_live_checks


def main() -> int:
    parser = argparse.ArgumentParser(description="Poll the live crawler endpoints until the deployment is reachable.")
    parser.add_argument("--timeout-seconds", type=int, default=600, help="Total time to wait before failing. Default: 600")
    parser.add_argument("--interval-seconds", type=int, default=20, help="Delay between checks. Default: 20")
    parser.add_argument("--request-timeout", type=float, default=15.0, help="Per-request timeout in seconds. Default: 15")
    args = parser.parse_args()

    deadline = time.monotonic() + max(args.timeout_seconds, 1)
    attempt = 0
    last_results = []

    while time.monotonic() <= deadline:
        attempt += 1
        print(f"\nAttempt {attempt}: checking live crawler endpoints...")
        last_results = run_live_checks(timeout=args.request_timeout, verify_content=False)
        print_live_summary(last_results)
        if all(result.ok for result in last_results):
            print("\nLive crawler endpoints are reachable. Continuing to strict validation.")
            return 0

        remaining = max(0, int(deadline - time.monotonic()))
        if remaining == 0:
            break
        sleep_for = min(args.interval_seconds, remaining)
        print(f"\nNot ready yet. Waiting {sleep_for} seconds before retrying...")
        time.sleep(sleep_for)

    print("\nTimed out waiting for the live crawler endpoints to become reachable.")
    if last_results:
        print_live_summary(last_results)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
