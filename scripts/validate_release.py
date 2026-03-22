#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from check_crawlers import print_live_summary, run_live_checks
from ebook_pipeline import run_validate_command


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the ebook subsystem release state")
    parser.add_argument("--workbook", help="Optional workbook path for workbook-to-master parity checks")
    parser.add_argument(
        "--post-deploy-live",
        action="store_true",
        help="After the normal repo validation passes, also check the published crawler URLs.",
    )
    parser.add_argument(
        "--strict-post-deploy-live",
        action="store_true",
        help="Fail the command when a published crawler URL is unreachable or drifts from the governed snapshot. Implies --post-deploy-live.",
    )
    parser.add_argument(
        "--skip-live-content",
        action="store_true",
        help="When running post-deploy live checks, confirm reachability only and skip content verification.",
    )
    parser.add_argument(
        "--live-timeout",
        type=float,
        default=15.0,
        help="HTTP timeout in seconds for post-deploy live crawler checks. Default: 15",
    )
    args = parser.parse_args()

    if args.strict_post_deploy_live:
        args.post_deploy_live = True

    workbook_path = Path(args.workbook).expanduser().resolve() if args.workbook else None
    exit_code = run_validate_command(workbook_path=workbook_path)
    if exit_code != 0:
        return exit_code

    if not args.post_deploy_live:
        return 0

    live_results = run_live_checks(timeout=args.live_timeout, verify_content=not args.skip_live_content)
    print_live_summary(live_results)
    live_failures = [result for result in live_results if not result.ok]
    if live_failures and args.strict_post_deploy_live:
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
