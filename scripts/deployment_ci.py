#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

WORKBOOK_ENV_VAR = "EBOOK_WORKBOOK_PATH"


def detect_workbook(explicit: str | None) -> Path | None:
    if explicit:
        candidate = Path(explicit).expanduser().resolve()
        if not candidate.exists():
            raise FileNotFoundError(f"Workbook not found: {candidate}")
        return candidate

    env_value = os.environ.get(WORKBOOK_ENV_VAR, "").strip()
    if env_value:
        candidate = Path(env_value).expanduser().resolve()
        if not candidate.exists():
            raise FileNotFoundError(f"{WORKBOOK_ENV_VAR} points to a missing file: {candidate}")
        return candidate

    candidates = sorted(ROOT.glob("*.xlsx")) + sorted(ROOT.glob("*.xlsm"))
    if len(candidates) == 1:
        return candidates[0].resolve()

    if len(candidates) > 1:
        candidate_list = ", ".join(path.name for path in candidates)
        raise ValueError(
            "Workbook source is ambiguous. Supply --workbook or set "
            f"{WORKBOOK_ENV_VAR}. Candidates in repo root: {candidate_list}"
        )

    return None


def run_step(label: str, command: list[str]) -> None:
    print(f"\n==> {label}")
    print("$", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the ebook deployment maintenance pipeline as a build-time CI gate."
    )
    parser.add_argument("--workbook", help="Workbook path. Falls back to EBOOK_WORKBOOK_PATH or a single workbook in the repo root. Multiple workbook candidates now fail fast.")
    parser.add_argument(
        "--allow-missing-workbook",
        action="store_true",
        help="Allow the build to continue without a workbook. Use only for local diagnostics.",
    )
    parser.add_argument(
        "--post-deploy-live",
        action="store_true",
        help="Also run live crawler validation after repo validation succeeds.",
    )
    parser.add_argument(
        "--strict-post-deploy-live",
        action="store_true",
        help="Fail on live crawler drift or reachability problems. Implies --post-deploy-live.",
    )
    parser.add_argument(
        "--skip-live-content",
        action="store_true",
        help="When running live validation, only confirm reachability and syntax.",
    )
    parser.add_argument(
        "--skip-live-page-smoke",
        action="store_true",
        help="When running post-deploy validation, skip curated live page marker checks.",
    )
    args = parser.parse_args()

    if args.strict_post_deploy_live:
        args.post_deploy_live = True

    # Smoke-import the core pipeline module so deployment fails fast on path/import issues.
    try:
        from scripts import ebook_pipeline  # noqa: F401
    except Exception as exc:  # pragma: no cover
        print(f"Core pipeline import failed: {exc}")
        return 1

    workbook_path = detect_workbook(args.workbook)
    if not workbook_path and not args.allow_missing_workbook:
        print("\n==> Workbook import failed")
        print(
            f"No workbook supplied via --workbook, {WORKBOOK_ENV_VAR}, or a single *.xlsx/*.xlsm file in the repo root. "
            "Governed builds require one explicit workbook source of truth."
        )
        return 1

    if workbook_path:
        run_step("Import workbook into the governed master record", [sys.executable, "scripts/import_ebook_workbook.py", str(workbook_path)])
    else:
        print("\n==> Workbook import skipped")
        print("Proceeding without workbook only because --allow-missing-workbook was supplied.")

    run_step("Regenerate canonical ebook pages and metadata", [sys.executable, "scripts/fix_book_head_metadata.py"])
    run_step("Rebuild derivative manifests and crawler snapshots", [sys.executable, "scripts/build_book_derivatives.py"])
    run_step("Synchronise redirects", [sys.executable, "scripts/sync_redirects.py"])
    run_step("Validate crawler snapshots", [sys.executable, "scripts/check_crawlers.py"])
    run_step("Validate transcript asset URLs", [sys.executable, "scripts/check_transcript_assets.py"])
    run_step("Inject featured book into homepage (source-of-truth sync)", [sys.executable, "scripts/inject_featured_book.py"])
    run_step("Inject shared partials (header + footer)", [sys.executable, "scripts/inject_partials.py"])
    run_step("Validate shared partials (header + footer - fail-fast gate)", [sys.executable, "scripts/inject_partials.py", "--validate"])
    run_step("Apply third-party script governance", [sys.executable, "scripts/govern_page_scripts.py"])
    run_step("Validate third-party script governance", [sys.executable, "scripts/govern_page_scripts.py", "--validate"])
    run_step("Run Phase 4A schema-markup gate", [sys.executable, "scripts/audits/schema_markup_gate.py", "--root", "."])

    validate_command = [sys.executable, "scripts/validate_release.py"]
    if workbook_path:
        validate_command.extend(["--workbook", str(workbook_path)])
    if args.post_deploy_live:
        validate_command.append("--post-deploy-live")
    if args.strict_post_deploy_live:
        validate_command.append("--strict-post-deploy-live")
    if args.skip_live_content:
        validate_command.append("--skip-live-content")
    if args.skip_live_page_smoke:
        validate_command.append("--skip-live-page-smoke")

    run_step("Run release validation", validate_command)
    print("\nDeployment CI pipeline passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
