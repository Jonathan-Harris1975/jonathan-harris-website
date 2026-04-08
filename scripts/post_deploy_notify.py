#!/usr/bin/env python3
"""Send the production post-deploy webhook once the live deployment gate has passed."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_WEBHOOK_URL = "https://hooks.jonathan-harris.online/b9gwu0nlgc751d"
DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_INITIAL_BACKOFF_SECONDS = 1.0
DEFAULT_MAX_BACKOFF_SECONDS = 16.0
TRANSIENT_HTTP_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
PRODUCTION_BRANCHES = {"main", "master"}


@dataclass(frozen=True)
class NotificationContext:
    repository: str
    branch: str
    commit_sha: str
    commit_message: str
    actor: str
    workflow: str
    run_id: str
    run_number: str
    run_url: str
    deployed_url: str


@dataclass(frozen=True)
class DeliveryFailure(Exception):
    message: str
    transient: bool

    def __str__(self) -> str:
        return self.message


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a post-deploy success webhook after the live production gate passes.")
    parser.add_argument("--webhook-url", default=DEFAULT_WEBHOOK_URL, help="Webhook destination. Defaults to the production post-deploy hook.")
    parser.add_argument("--deployed-url", default=default_deployed_url(), help="Published production URL included in the payload.")
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS, help=f"Per-request timeout in seconds. Default: {DEFAULT_TIMEOUT_SECONDS}")
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS, help=f"Maximum delivery attempts. Default: {DEFAULT_MAX_ATTEMPTS}")
    parser.add_argument(
        "--initial-backoff-seconds",
        type=float,
        default=DEFAULT_INITIAL_BACKOFF_SECONDS,
        help=f"Initial exponential backoff in seconds. Default: {DEFAULT_INITIAL_BACKOFF_SECONDS}",
    )
    parser.add_argument(
        "--max-backoff-seconds",
        type=float,
        default=DEFAULT_MAX_BACKOFF_SECONDS,
        help=f"Maximum backoff delay in seconds. Default: {DEFAULT_MAX_BACKOFF_SECONDS}",
    )
    return parser.parse_args()


def default_deployed_url() -> str:
    try:
        from scripts.ebook_pipeline import SITE_URL

        if isinstance(SITE_URL, str) and SITE_URL.strip():
            return SITE_URL.strip()
    except Exception:
        pass
    return "https://jonathan-harris.online"


def parse_branch_name() -> str:
    branch = env("GITHUB_REF_NAME")
    if branch:
        return branch
    ref = env("GITHUB_REF")
    if ref.startswith("refs/heads/"):
        return ref.split("/", 2)[2]
    return ref


def load_event_payload() -> dict[str, Any]:
    event_path = env("GITHUB_EVENT_PATH")
    if not event_path:
        return {}
    path = Path(event_path)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[WARN] Could not read GitHub event payload from {path}: {exc}")
        return {}


def extract_commit_message(event_payload: dict[str, Any]) -> str:
    head_commit = event_payload.get("head_commit")
    if isinstance(head_commit, dict):
        message = str(head_commit.get("message") or "").strip()
        if message:
            return message

    commits = event_payload.get("commits")
    if isinstance(commits, list):
        for commit in reversed(commits):
            if isinstance(commit, dict):
                message = str(commit.get("message") or "").strip()
                if message:
                    return message

    return env("GITHUB_COMMIT_MESSAGE")


def build_run_url(repository: str, run_id: str) -> str:
    if not repository or not run_id:
        return ""
    server_url = env("GITHUB_SERVER_URL", "https://github.com")
    return f"{server_url}/{repository}/actions/runs/{run_id}"


def validate_github_context(branch: str) -> None:
    if env("GITHUB_ACTIONS").lower() != "true":
        return

    event_name = env("GITHUB_EVENT_NAME")
    if event_name != "push":
        raise DeliveryFailure(
            f"Refusing to notify because GITHUB_EVENT_NAME='{event_name}' is not a production push.",
            transient=False,
        )

    if branch not in PRODUCTION_BRANCHES:
        raise DeliveryFailure(
            f"Refusing to notify because branch '{branch}' is not one of {sorted(PRODUCTION_BRANCHES)}.",
            transient=False,
        )


def build_context(deployed_url: str) -> NotificationContext:
    """Collect the GitHub Actions metadata required by the webhook payload."""
    event_payload = load_event_payload()
    branch = parse_branch_name()
    validate_github_context(branch)

    repository = env("GITHUB_REPOSITORY")
    run_id = env("GITHUB_RUN_ID")
    return NotificationContext(
        repository=repository,
        branch=branch,
        commit_sha=env("GITHUB_SHA"),
        commit_message=extract_commit_message(event_payload),
        actor=env("GITHUB_ACTOR"),
        workflow=env("GITHUB_WORKFLOW"),
        run_id=run_id,
        run_number=env("GITHUB_RUN_NUMBER"),
        run_url=build_run_url(repository, run_id),
        deployed_url=deployed_url,
    )


def build_payload(context: NotificationContext) -> dict[str, str]:
    return {
        "event": "post_deploy_success",
        "repository": context.repository,
        "branch": context.branch,
        "commit_sha": context.commit_sha,
        "commit_message": context.commit_message,
        "actor": context.actor,
        "workflow": context.workflow,
        "run_id": context.run_id,
        "run_number": context.run_number,
        "run_url": context.run_url,
        "deployed_url": context.deployed_url,
        "environment": "production",
        "status": "success",
        "timestamp_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


def should_retry_http_status(status_code: int) -> bool:
    return status_code in TRANSIENT_HTTP_STATUS_CODES


def should_retry_url_error(exc: error.URLError) -> bool:
    reason = exc.reason
    if isinstance(reason, TimeoutError):
        return True
    if isinstance(reason, OSError):
        return True
    return False


def post_payload(webhook_url: str, payload: dict[str, str], timeout_seconds: float) -> None:
    data = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    req = request.Request(
        webhook_url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "JonathanHarrisPostDeployNotifier/1.0",
        },
    )

    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            status_code = response.getcode()
            response_body = response.read().decode("utf-8", errors="replace").strip()
    except error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace").strip()
        message = f"Webhook returned HTTP {exc.code}."
        if response_body:
            message = f"{message} Response body: {response_body[:500]}"
        raise DeliveryFailure(message, transient=should_retry_http_status(exc.code)) from exc
    except error.URLError as exc:
        raise DeliveryFailure(f"Webhook request failed: {exc.reason}", transient=should_retry_url_error(exc)) from exc
    except TimeoutError as exc:
        raise DeliveryFailure("Webhook request timed out.", transient=True) from exc

    if status_code < 200 or status_code >= 300:
        message = f"Webhook returned unexpected HTTP {status_code}."
        if response_body:
            message = f"{message} Response body: {response_body[:500]}"
        raise DeliveryFailure(message, transient=should_retry_http_status(status_code))

    print(f"[INFO] Webhook delivered successfully with HTTP {status_code}.")
    if response_body:
        print(f"[INFO] Webhook response body: {response_body[:500]}")


def deliver_with_retries(
    webhook_url: str,
    payload: dict[str, str],
    timeout_seconds: float,
    max_attempts: int,
    initial_backoff_seconds: float,
    max_backoff_seconds: float,
) -> None:
    attempts = max(1, max_attempts)
    next_backoff = max(initial_backoff_seconds, 0.0)

    for attempt in range(1, attempts + 1):
        print(f"[INFO] Delivery attempt {attempt}/{attempts} to {webhook_url}")
        try:
            post_payload(webhook_url=webhook_url, payload=payload, timeout_seconds=timeout_seconds)
            return
        except DeliveryFailure as exc:
            is_last_attempt = attempt == attempts
            print(f"[WARN] {exc}")
            if is_last_attempt:
                raise
            if not exc.transient:
                raise

            sleep_seconds = min(next_backoff, max_backoff_seconds)
            if sleep_seconds > 0:
                print(f"[INFO] Retrying in {sleep_seconds:.1f} seconds...")
                time.sleep(sleep_seconds)
            next_backoff = max(next_backoff * 2, next_backoff + 1.0)


def main() -> int:
    args = parse_args()
    try:
        context = build_context(deployed_url=args.deployed_url)
        payload = build_payload(context)
    except DeliveryFailure as exc:
        print(f"[ERROR] {exc}")
        return 1

    print("[INFO] Prepared post-deploy notification payload:")
    print(json.dumps(payload, indent=2, sort_keys=True))

    try:
        deliver_with_retries(
            webhook_url=args.webhook_url,
            payload=payload,
            timeout_seconds=max(args.timeout_seconds, 1.0),
            max_attempts=max(args.max_attempts, 1),
            initial_backoff_seconds=max(args.initial_backoff_seconds, 0.0),
            max_backoff_seconds=max(args.max_backoff_seconds, 0.0),
        )
    except DeliveryFailure as exc:
        print(f"[ERROR] Post-deploy webhook notification failed: {exc}")
        return 1

    print("[INFO] Post-deploy webhook notification completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
