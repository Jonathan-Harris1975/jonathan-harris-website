#!/usr/bin/env python3
import argparse
from pathlib import Path
from ebook_pipeline import run_validate_command


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the ebook subsystem release state")
    parser.add_argument("--workbook", help="Optional workbook path for workbook-to-master parity checks")
    args = parser.parse_args()
    workbook_path = Path(args.workbook).expanduser().resolve() if args.workbook else None
    return run_validate_command(workbook_path=workbook_path)


if __name__ == '__main__':
    raise SystemExit(main())
