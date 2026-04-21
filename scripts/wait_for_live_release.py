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
from scripts.maintenance.check_redirect_chains import run_redirect_checks


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Poll the live crawler endpoints until the deployment is ready. By default this waits "
            "for reachability only; optional flags can require governed content parity and the "
            "support alias redirect contract as well."
        )
    )
    parser.add_argument("--timeout-seconds", type=int, default=600, help="Total time to wait before failing. Default: 600")
    parser.add_argument("--interval-seconds", type=int, default=20, help="Delay between checks. Default: 20")
    parser.add_argument("--request-timeout", type=float, default=15.0, help="Per-request timeout in seconds. Default: 15")
    parser.add_argument(
        "--require-content-match",
        action="store_true",
        help="Wait until the governed live crawler bodies match the repo snapshots, not just reachability.",
    )
    parser.add_argument(
        "--require-redirect-contract",
        action="store_true",
        help="Also wait until the governed live support alias contract passes.",
    )
    args = parser.parse_args()

    deadline = time.monotonic() + max(args.timeout_seconds, 1)
    attempt = 0
    last_results = []
    last_redirect_failures: list[str] = []

    while time.monotonic() <= deadline:
        attempt += 1
        print(f"\nAttempt {attempt}: checking live crawler endpoints...")
        last_results = run_live_checks(timeout=args.request_timeout, verify_content=args.require_content_match)
        print_live_summary(last_results)

        content_ready = all(result.ok for result in last_results)
        redirects_ready = True
        last_redirect_failures = []
        if content_ready and args.require_redirect_contract:
            last_redirect_failures = run_redirect_checks(args.request_timeout)
            redirects_ready = not last_redirect_failures
            if redirects_ready:
                print("Live redirect alias contract check passed.")
            else:
                print("Live redirect alias contract is not ready yet:")
                for failure in last_redirect_failures:
                    print(f"- {failure}")

        if content_ready and redirects_ready:
            ready_message = "Live crawler endpoints are ready"
            if args.require_content_match:
                ready_message += " and match the governed repo snapshots"
            else:
                ready_message += " and are reachable"
            if args.require_redirect_contract:
                ready_message += ", including the alias redirect contract"
            print(f"\n{ready_message}. Continuing to strict validation.")
            return 0

        remaining = max(0, int(deadline - time.monotonic()))
        if remaining == 0:
            break
        sleep_for = min(args.interval_seconds, remaining)
        print(f"\nNot ready yet. Waiting {sleep_for} seconds before retrying...")
        time.sleep(sleep_for)

    print("\nTimed out waiting for the live crawler release contract to become ready.")
    if last_results:
        print_live_summary(last_results)
    if last_redirect_failures:
        print("Live redirect alias contract failures at timeout:")
        for failure in last_redirect_failures:
            print(f"- {failure}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
