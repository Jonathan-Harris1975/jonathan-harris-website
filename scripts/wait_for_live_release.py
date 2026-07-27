#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib import error, parse, request

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.check_crawlers import print_live_summary, run_live_checks
from scripts.maintenance.check_redirect_chains import run_redirect_checks

DEFAULT_RELEASE_URL = "https://jonathan-harris.online/release.json"


def expected_release_sha(explicit_sha: str) -> str:
    return explicit_sha.strip() or os.environ.get("GITHUB_SHA", "").strip()


def live_release_matches(release_url: str, expected_sha: str, request_timeout: float) -> tuple[bool, str]:
    if not expected_sha:
        return False, "No expected release SHA was supplied and GITHUB_SHA is empty."

    separator = "&" if "?" in release_url else "?"
    cache_busted_url = f"{release_url}{separator}expected={parse.quote(expected_sha)}&t={int(time.time())}"
    req = request.Request(
        cache_busted_url,
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "User-Agent": "JonathanHarrisReleaseGate/1.0",
        },
    )
    try:
        with request.urlopen(req, timeout=max(request_timeout, 1.0)) as response:
            status = response.getcode()
            body = response.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        return False, f"release marker returned HTTP {exc.code}"
    except (error.URLError, TimeoutError, OSError) as exc:
        return False, f"release marker request failed: {exc}"

    if status != 200:
        return False, f"release marker returned HTTP {status}"
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return False, "release marker was not valid JSON"

    live_sha = str(payload.get("commit_sha") or "").strip()
    if live_sha != expected_sha:
        return False, f"live commit is {live_sha or '<missing>'}; waiting for {expected_sha}"
    return True, f"live release marker matches commit {expected_sha}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Poll production until the intended deployment is ready. The release-SHA check prevents "
            "an older deployment from passing merely because unchanged crawler files already match."
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
    parser.add_argument(
        "--require-release-sha",
        action="store_true",
        help="Require production /release.json to report the exact commit being validated.",
    )
    parser.add_argument(
        "--expected-sha",
        default="",
        help="Expected production commit SHA. Defaults to GITHUB_SHA.",
    )
    parser.add_argument(
        "--release-url",
        default=DEFAULT_RELEASE_URL,
        help=f"Release marker URL. Default: {DEFAULT_RELEASE_URL}",
    )
    parser.add_argument(
        "--stabilisation-seconds",
        type=int,
        default=0,
        help="Extra settling time after the exact release is first observed, before validation continues.",
    )
    args = parser.parse_args()

    expected_sha = expected_release_sha(args.expected_sha)
    if args.require_release_sha and not expected_sha:
        print("Cannot require a release SHA because neither --expected-sha nor GITHUB_SHA is available.")
        return 2

    deadline = time.monotonic() + max(args.timeout_seconds, 1)
    attempt = 0
    last_results = []
    last_redirect_failures: list[str] = []
    release_ready = not args.require_release_sha
    last_release_message = "release SHA check not requested"

    while time.monotonic() <= deadline:
        attempt += 1
        print(f"\nAttempt {attempt}: checking production readiness...")

        if args.require_release_sha:
            release_ready, last_release_message = live_release_matches(
                release_url=args.release_url,
                expected_sha=expected_sha,
                request_timeout=args.request_timeout,
            )
            print(f"Release marker: {last_release_message}")
            if not release_ready:
                remaining = max(0, int(deadline - time.monotonic()))
                if remaining == 0:
                    break
                sleep_for = min(args.interval_seconds, remaining)
                print(f"Not the new Pages release yet. Waiting {sleep_for} seconds before retrying...")
                time.sleep(sleep_for)
                continue

        print("Checking live crawler endpoints...")
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

        if release_ready and content_ready and redirects_ready:
            settle = max(args.stabilisation_seconds, 0)
            if settle:
                remaining = max(0, int(deadline - time.monotonic()))
                if remaining < settle:
                    print(f"Release is visible but only {remaining}s remain, less than the requested {settle}s stabilisation window.")
                    break
                print(f"\nExact release is live. Allowing {settle} seconds for edge propagation before continuing...")
                time.sleep(settle)

                if args.require_release_sha:
                    still_ready, message = live_release_matches(args.release_url, expected_sha, args.request_timeout)
                    print(f"Release marker after stabilisation: {message}")
                    if not still_ready:
                        release_ready = False
                        continue

            ready_message = "Production is serving the intended release"
            if args.require_content_match:
                ready_message += " and crawler content matches the governed repo snapshots"
            if args.require_redirect_contract:
                ready_message += ", including the alias redirect contract"
            print(f"\n{ready_message}. Continuing to strict validation and purge.")
            return 0

        remaining = max(0, int(deadline - time.monotonic()))
        if remaining == 0:
            break
        sleep_for = min(args.interval_seconds, remaining)
        print(f"\nNot ready yet. Waiting {sleep_for} seconds before retrying...")
        time.sleep(sleep_for)

    print("\nTimed out waiting for the intended production release to become ready.")
    if args.require_release_sha:
        print(f"Release marker status: {last_release_message}")
    if last_results:
        print_live_summary(last_results)
    if last_redirect_failures:
        print("Live redirect alias contract failures at timeout:")
        for failure in last_redirect_failures:
            print(f"- {failure}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
