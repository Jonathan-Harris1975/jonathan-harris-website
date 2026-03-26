#!/usr/bin/env python3
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
from scripts.ebook_pipeline import run_build_derivatives_command


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild derived ebook JSON, manifests, crawler files, and governed discovery pages")
    parser.add_argument("--check", action="store_true", help="Validate derivative outputs after generation")
    parser.add_argument("--workbook", help="Optional workbook path for parity validation")
    return run_build_derivatives_command(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
