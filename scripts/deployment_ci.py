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
CANONICAL_WORKBOOK = ROOT / "jonathan-harris-site-url-inventory-remediated-release-ready.xlsx"
MANUSCRIPT_MANIFEST = ROOT / "scripts" / "data" / "manuscripts.json"
MANUSCRIPT_SAMPLE_CACHE = ROOT / "data" / "book-sample-chapters.json"


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

    if CANONICAL_WORKBOOK.exists():
        return CANONICAL_WORKBOOK.resolve()

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
    parser.add_argument(
        "--skip-manuscript-sync",
        action="store_true",
        help="Skip remote manuscript download/extraction. Local diagnostics only; governed production builds require every advertised sample to be a genuine extracted chapter, but individual books may omit a sample when extraction is unavailable.",
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

    try:
        if workbook_path:
            run_step("Import workbook into the governed master record", [sys.executable, "scripts/import_ebook_workbook.py", str(workbook_path)])
            run_step("Generate private manuscript manifest", [sys.executable, "scripts/generate_manuscript_manifest.py", str(workbook_path)])
            if args.skip_manuscript_sync:
                print("\n==> Manuscript sample sync skipped")
                print("Local diagnostics mode: generated sample pages will not be release-ready without a genuine chapter cache.")
            else:
                run_step(
                    "Extract genuine sample chapters from manuscript PDFs",
                    [sys.executable, "scripts/sync_manuscript_samples.py", "--allow-partial"],
                )
        else:
            print("\n==> Workbook import skipped")
            print("Proceeding without workbook only because --allow-missing-workbook was supplied.")

        run_step("Regenerate canonical ebook pages and metadata", [sys.executable, "scripts/fix_book_head_metadata.py"])
        run_step("Generate curated ebook reading paths", [sys.executable, "scripts/generate_ebook_bundles.py"])
        run_step("Test podcast RSS fallback parser", [sys.executable, "scripts/test_sync_podcast_episodes.py"])
        run_step("Refresh podcast RSS fallback", [sys.executable, "scripts/sync_podcast_episodes.py"])
        run_step("Generate growth, evidence and conversion assets", [sys.executable, "scripts/generate_growth_assets.py"])
        run_step("Generate downloadable AI glossary PDF", [sys.executable, "scripts/generate_ai_glossary_pdf.py"])
        run_step("Mark stale blog snapshots honestly", [sys.executable, "scripts/mark_stale_blog_snapshot.py"])
        run_step("Validate governed ebook route integrity", [sys.executable, "scripts/check_ebook_route_integrity.py"])
        run_step("Rebuild derivative manifests and crawler snapshots", [sys.executable, "scripts/build_book_derivatives.py"])
        run_step("Synchronise redirects", [sys.executable, "scripts/sync_redirects.py"])
        run_step("Validate crawler snapshots", [sys.executable, "scripts/check_crawlers.py"])
        run_step("Validate transcript asset URLs", [sys.executable, "scripts/check_transcript_assets.py"])
        run_step("Inject featured book into homepage (source-of-truth sync)", [sys.executable, "scripts/inject_featured_book.py"])
        run_step("Inject shared partials (header + footer)", [sys.executable, "scripts/inject_partials.py"])
        run_step("Validate shared partials (header + footer - fail-fast gate)", [sys.executable, "scripts/inject_partials.py", "--validate"])
        run_step("Validate shared chrome visibility and spacing", [sys.executable, "scripts/check_shared_chrome_layout.py"])
        run_step("Check CSS size budget", [sys.executable, "scripts/check_css_budget.py", "--check"])
        run_step("Check core colour contrast", [sys.executable, "scripts/check_colour_contrast.py"])
        run_step("Apply third-party script governance", [sys.executable, "scripts/govern_page_scripts.py"])
        run_step("Validate third-party script governance", [sys.executable, "scripts/govern_page_scripts.py", "--validate"])
        run_step("Run growth regression contracts", [sys.executable, "scripts/test_growth_contracts.py"])
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
    finally:
        # Manuscript URLs and the extraction cache are build-time inputs. The public
        # artefact is the generated HTML chapter page, so private/redundant source
        # data is always removed even when a later release gate fails.
        for path in (MANUSCRIPT_MANIFEST, MANUSCRIPT_SAMPLE_CACHE):
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                print(f"WARN: could not remove temporary manuscript build file {path}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
