#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse

from scripts.check_crawlers import print_live_summary, run_live_checks
from scripts.check_live_pages import print_results as print_live_page_summary, run_checks as run_live_page_checks
from scripts.ebook_pipeline import run_validate_command
from scripts.maintenance.check_redirect_chains import run_redirect_checks


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
        help="Fail the command when published crawler checks or curated live page/API checks fail. Implies --post-deploy-live.",
    )
    parser.add_argument(
        "--skip-live-content",
        action="store_true",
        help="When running post-deploy live crawler checks, confirm reachability only and skip content verification.",
    )
    parser.add_argument(
        "--skip-live-page-smoke",
        action="store_true",
        help="When running post-deploy live validation, skip curated live page and API contract checks.",
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

    page_failures = []
    if not args.skip_live_page_smoke:
        page_results = run_live_page_checks(timeout=args.live_timeout, workbook_path=workbook_path)
        print_live_page_summary(page_results)
        page_failures = [result for result in page_results if not result.ok]

    redirect_failures: list[str] = []
    if args.strict_post_deploy_live:
        redirect_failures = run_redirect_checks(args.live_timeout)
        if redirect_failures:
            for error in redirect_failures:
                print(f"[FAIL] Live redirect contract: {error}")
        else:
            print("[PASS] Live redirect contract: all governed redirect chains resolved correctly.")

    if (live_failures or page_failures or redirect_failures) and args.strict_post_deploy_live:
        return 1

    if args.strict_post_deploy_live:
        print("Strict post-deploy live validation passed.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
