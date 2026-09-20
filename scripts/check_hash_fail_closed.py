#!/usr/bin/env python3
"""Prove pip rejects a candidate artefact whose SHA-256 is not approved."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="website-hash-fail-closed-") as tmp:
        workspace = Path(tmp)
        # pip identifies the candidate from the filename before it attempts to
        # parse wheel contents, so a tiny local fixture is sufficient and keeps
        # this negative test completely offline and deterministic.
        candidate = workspace / "pillow-12.3.0-py3-none-any.whl"
        candidate.write_bytes(b"deliberately untrusted candidate\n")
        requirements = workspace / "requirements-corrupt.txt"
        requirements.write_text(
            "pillow==12.3.0 \\\n"
            "    --hash=sha256:" + ("0" * 64) + "\n",
            encoding="utf-8",
        )

        command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-index",
            "--no-deps",
            "--ignore-installed",
            "--require-hashes",
            "--find-links",
            str(workspace),
            "-r",
            str(requirements),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        output = completed.stdout + completed.stderr
        if completed.returncode == 0:
            raise SystemExit("Hash enforcement failure: pip accepted a candidate with a deliberately corrupt hash")
        if "DO NOT MATCH THE HASHES" not in output and "THESE PACKAGES DO NOT MATCH THE HASHES" not in output:
            raise SystemExit(
                "Hash enforcement negative test failed for an unexpected reason.\n"
                + output[-2000:]
            )

    print("Hash fail-closed check OK: pip rejected the deliberately mismatched candidate artefact.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
