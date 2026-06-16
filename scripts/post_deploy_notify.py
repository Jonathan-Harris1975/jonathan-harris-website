#!/usr/bin/env python3
"""Send post-deploy notifications after the live production gate has passed.

This script supports two delivery targets:
1. The legacy post-deploy success webhook used for downstream automation.
2. A Cloudflare purge endpoint exposed by the AI Management Suite at /cloudflare/purge.
"""
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
from urllib import error, parse, request

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_WEBHOOK_URL = ""
DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_INITIAL_BACKOFF_SECONDS = 1.0
DEFAULT_MAX_BACKOFF_SECONDS = 16.0
TRANSIENT_HTTP_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
PRODUCTION_BRANCHES = {"main", "master"}
CLOUDFLARE_PURGE_ENDPOINT_ENV = "CLOUDFLARE_PURGE_ENDPOINT_URL"
CLOUDFLARE_PURGE_SECRET_ENV = "CLOUDFLARE_PURGE_SHARED_SECRET"
CLOUDFLARE_PURGE_HOSTS_ENV = "CLOUDFLARE_PURGE_HOSTS"
POST_DEPLOY_WEBHOOK_URL_ENV = "POST_DEPLOY_WEBHOOK_URL"


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


def getenv_or_default(name: str, default: str = "") -> str:
    if name in os.environ:
        return os.environ.get(name, "").strip()
    return default


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send post-deploy notifications after the live production gate passes.")
    parser.add_argument(
        "--webhook-url",
        default=getenv_or_default(POST_DEPLOY_WEBHOOK_URL_ENV, DEFAULT_WEBHOOK_URL),
        help=(
            "Optional legacy post-deploy webhook destination. "
            f"Defaults to {POST_DEPLOY_WEBHOOK_URL_ENV} when set; otherwise delivery is skipped. "
            "No webhook endpoint is embedded in the repository."
        ),
    )
    parser.add_argument(
        "--cloudflare-purge-endpoint",
        default=env(CLOUDFLARE_PURGE_ENDPOINT_ENV),
        help=(
            "Optional Cloudflare purge endpoint, usually the AI Management Suite /cloudflare/purge route "
            f"or a Hookdeck URL that forwards to it. Defaults to {CLOUDFLARE_PURGE_ENDPOINT_ENV}."
        ),
    )
    parser.add_argument(
        "--cloudflare-purge-secret",
        default=env(CLOUDFLARE_PURGE_SECRET_ENV),
        help=(
            "Optional shared secret sent as x-cloudflare-purge-secret when purging through the AI Management Suite. "
            f"Defaults to {CLOUDFLARE_PURGE_SECRET_ENV}."
        ),
    )
    parser.add_argument(
        "--cloudflare-purge-hosts",
        default=env(CLOUDFLARE_PURGE_HOSTS_ENV),
        help=(
            "Optional comma-separated hostnames to purge. Defaults to the deployed URL hostname when omitted. "
            f"Defaults to {CLOUDFLARE_PURGE_HOSTS_ENV}."
        ),
    )
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


def build_cloudflare_purge_payload(hosts_argument: str, deployed_url: str) -> dict[str, list[str]]:
    if hosts_argument:
        hosts = [item.strip() for item in hosts_argument.split(",") if item.strip()]
    else:
        parsed = parse.urlparse(deployed_url)
        hostname = (parsed.hostname or "").strip()
        hosts = [hostname] if hostname else []

    if not hosts:
        raise DeliveryFailure(
            "Cloudflare purge endpoint was configured, but no purge hosts could be derived from --deployed-url or --cloudflare-purge-hosts.",
            transient=False,
        )

    return {"hosts": hosts}


def should_retry_http_status(status_code: int) -> bool:
    return status_code in TRANSIENT_HTTP_STATUS_CODES


def should_retry_url_error(exc: error.URLError) -> bool:
    reason = exc.reason
    if isinstance(reason, TimeoutError):
        return True
    if isinstance(reason, OSError):
        return True
    return False


def post_json(target_url: str, payload: dict[str, Any], timeout_seconds: float, headers: dict[str, str] | None = None, label: str = "Webhook") -> None:
    request_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "JonathanHarrisPostDeployNotifier/1.1",
    }
    if headers:
        request_headers.update({key: value for key, value in headers.items() if value is not None and str(value).strip()})

    data = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    req = request.Request(
        target_url,
        data=data,
        method="POST",
        headers=request_headers,
    )

    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            status_code = response.getcode()
            response_body = response.read().decode("utf-8", errors="replace").strip()
    except error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace").strip()
        message = f"{label} returned HTTP {exc.code}."
        if response_body:
            message = f"{message} Response body: {response_body[:500]}"
        raise DeliveryFailure(message, transient=should_retry_http_status(exc.code)) from exc
    except error.URLError as exc:
        raise DeliveryFailure(f"{label} request failed: {exc.reason}", transient=should_retry_url_error(exc)) from exc
    except TimeoutError as exc:
        raise DeliveryFailure(f"{label} request timed out.", transient=True) from exc

    if status_code < 200 or status_code >= 300:
        message = f"{label} returned unexpected HTTP {status_code}."
        if response_body:
            message = f"{message} Response body: {response_body[:500]}"
        raise DeliveryFailure(message, transient=should_retry_http_status(status_code))

    print(f"[INFO] {label} delivered successfully with HTTP {status_code}.")
    if response_body:
        print(f"[INFO] {label} response body: {response_body[:500]}")


def deliver_with_retries(
    target_url: str,
    payload: dict[str, Any],
    timeout_seconds: float,
    max_attempts: int,
    initial_backoff_seconds: float,
    max_backoff_seconds: float,
    headers: dict[str, str] | None = None,
    label: str = "Webhook",
) -> None:
    attempts = max(1, max_attempts)
    next_backoff = max(initial_backoff_seconds, 0.0)

    for attempt in range(1, attempts + 1):
        print(f"[INFO] {label} delivery attempt {attempt}/{attempts} to {target_url}")
        try:
            post_json(target_url=target_url, payload=payload, timeout_seconds=timeout_seconds, headers=headers, label=label)
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


def maybe_deliver_legacy_webhook(args: argparse.Namespace, payload: dict[str, str]) -> None:
    webhook_url = args.webhook_url.strip()
    if not webhook_url:
        print("[INFO] Legacy post-deploy webhook skipped because no webhook URL was configured.")
        return

    deliver_with_retries(
        target_url=webhook_url,
        payload=payload,
        timeout_seconds=max(args.timeout_seconds, 1.0),
        max_attempts=max(args.max_attempts, 1),
        initial_backoff_seconds=max(args.initial_backoff_seconds, 0.0),
        max_backoff_seconds=max(args.max_backoff_seconds, 0.0),
        label="Legacy webhook",
    )


def maybe_deliver_cloudflare_purge(args: argparse.Namespace) -> None:
    endpoint = args.cloudflare_purge_endpoint.strip()
    if not endpoint:
        print("[INFO] Cloudflare purge skipped because no purge endpoint was configured.")
        return

    purge_payload = build_cloudflare_purge_payload(args.cloudflare_purge_hosts, args.deployed_url)
    purge_headers: dict[str, str] = {}
    if args.cloudflare_purge_secret.strip():
        purge_headers["x-cloudflare-purge-secret"] = args.cloudflare_purge_secret.strip()

    print("[INFO] Prepared Cloudflare purge payload:")
    print(json.dumps(purge_payload, indent=2, sort_keys=True))

    deliver_with_retries(
        target_url=endpoint,
        payload=purge_payload,
        timeout_seconds=max(args.timeout_seconds, 1.0),
        max_attempts=max(args.max_attempts, 1),
        initial_backoff_seconds=max(args.initial_backoff_seconds, 0.0),
        max_backoff_seconds=max(args.max_backoff_seconds, 0.0),
        headers=purge_headers,
        label="Cloudflare purge",
    )


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
        maybe_deliver_cloudflare_purge(args)
        maybe_deliver_legacy_webhook(args, payload)
    except DeliveryFailure as exc:
        print(f"[ERROR] Post-deploy notification failed: {exc}")
        return 1

    print("[INFO] Post-deploy notification completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
