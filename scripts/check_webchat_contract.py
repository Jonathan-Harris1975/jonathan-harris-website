#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = {
    "assets/js/cognipal-webchat.min.js": ["/api/cognipal/message", "/api/cognipal/sync", "Talk to a person", "CogniPal"],
    "assets/css/cognipal-webchat.min.css": [".jh-cognipal__launcher", ".jh-cognipal__panel"],
    "functions/_shared/cognipal.js": ["x-coginpal-signature", "AIMS_COMMS_HUB_BASE_URL", "COMMS_HUB_COGINPAL_WEBHOOK_SECRET"],
    "functions/api/cognipal/message.js": ["/comms-hub/intake/chat"],
    "functions/api/cognipal/sync.js": ["/comms-hub/intake/chat/sync"],
    "assets/js/script-governance.min.js": ["cognipal-webchat.min.js", "cognipal-webchat.min.css"],
    "privacy-policy/index.html": ["CogniPal", "AIMS Communications Hub"],
}


def main() -> int:
    failures: list[str] = []
    for rel, markers in REQUIRED.items():
        path = ROOT / rel
        if not path.is_file():
            failures.append(f"missing required webchat file: {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                failures.append(f"{rel} missing marker: {marker}")

    html_with_botsailor = []
    for page in ROOT.rglob("*.html"):
        if "botsailor" in page.read_text(encoding="utf-8").lower():
            html_with_botsailor.append(page.relative_to(ROOT).as_posix())
    if html_with_botsailor:
        failures.append("BotSailor remains in HTML: " + ", ".join(html_with_botsailor[:10]))

    headers = (ROOT / "_headers").read_text(encoding="utf-8")
    if "botsailor" in headers.lower():
        failures.append("BotSailor remains in CSP headers")
    if "connect-src 'self'" not in headers:
        failures.append("CSP must allow same-origin CogniPal API calls")

    governance = (ROOT / "scripts" / "govern_page_scripts.py").read_text(encoding="utf-8")
    if "missing BotSailor script" in governance:
        failures.append("script governance still requires BotSailor")

    if failures:
        for failure in failures:
            print(f"[FAIL] {failure}")
        print(f"\nWebchat contract failed: {len(failures)} issue(s).")
        return 1

    print("Webchat contract passed: first-party CogniPal is embedded and BotSailor is absent from public runtime surfaces.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
