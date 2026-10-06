#!/usr/bin/env python3
"""Durable single-writer ownership leases stored on real GitHub issues/PRs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.error
import urllib.request
import uuid
from typing import Any

API = "https://api.github.com"
REPO = os.environ.get("REPO") or os.environ.get("GITHUB_REPOSITORY", "")
TOKEN = os.environ.get("GH_TOKEN", "")
MARKER = "<!-- autonomy-lease:v1 "


def fingerprint(repository: str, category: str, scope: str, source_sha: str) -> str:
    raw = json.dumps(
        [repository, category, scope, source_sha],
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def marker_payload(body: str) -> dict[str, Any] | None:
    if MARKER not in body:
        return None
    try:
        raw = body.split(MARKER, 1)[1].split(" -->", 1)[0]
        data = json.loads(raw)
    except Exception:
        return None
    return data if data.get("version") == 1 and data.get("fingerprint") else None


def _request(method: str, path: str, data: dict | None = None):
    encoded = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(API + path, data=encoded, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:300]
        raise RuntimeError(f"GitHub API HTTP {exc.code}: {detail}") from exc


def all_lease_comments() -> list[dict]:
    comments: list[dict] = []
    for page in range(1, 11):
        rows = _request(
            "GET",
            f"/repos/{REPO}/issues/comments?per_page=100&page={page}",
        )
        comments.extend(rows)
        if len(rows) < 100:
            break
    return [item for item in comments if marker_payload(item.get("body", ""))]


def active_for_fingerprint(fp: str) -> dict | None:
    state = None
    for comment in sorted(all_lease_comments(), key=lambda item: int(item["id"])):
        payload = marker_payload(comment.get("body", ""))
        if payload and payload.get("fingerprint") == fp:
            state = {
                **payload,
                "comment_id": comment["id"],
                "issue_url": comment.get("issue_url"),
            }
    return state if state and state.get("status") == "active" else None


def post_state(issue: int, payload: dict) -> dict:
    body = MARKER + json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
    ) + " -->"
    _request(
        "POST",
        f"/repos/{REPO}/issues/{issue}/comments",
        {"body": body},
    )
    return payload


def claim(
    issue: int,
    owner: str,
    category: str,
    scope: str,
    source_sha: str,
) -> dict:
    fp = fingerprint(REPO, category, scope, source_sha)
    current = active_for_fingerprint(fp)
    if current:
        if current.get("owner") != owner:
            raise RuntimeError(f"fingerprint already owned by {current.get('owner')}")
        return current
    payload = {
        "version": 1,
        "status": "active",
        "fingerprint": fp,
        "owner": owner,
        "fence": uuid.uuid4().hex,
        "category": category,
        "scope": scope,
        "source_sha": source_sha,
        "source_issue": issue,
    }
    return post_state(issue, payload)


def bind(issue: int, owner: str, fp: str, implementation_pr: int) -> dict:
    current = active_for_fingerprint(fp)
    if not current or current.get("owner") != owner:
        raise RuntimeError("active lease owner mismatch")
    payload = {
        key: value
        for key, value in current.items()
        if key not in {"comment_id", "issue_url"}
    }
    payload["implementation_pr"] = implementation_pr
    return post_state(issue, payload)


def release(issue: int, owner: str, fp: str, reason: str) -> dict:
    current = active_for_fingerprint(fp)
    if not current or current.get("owner") != owner:
        raise RuntimeError("active lease owner mismatch")
    payload = {
        key: value
        for key, value in current.items()
        if key not in {"comment_id", "issue_url"}
    }
    payload.update({"status": "released", "reason": reason})
    return post_state(issue, payload)


def previous_writer_inactive(current: dict) -> bool:
    implementation = current.get("implementation_pr")
    if implementation:
        pr = _request("GET", f"/repos/{REPO}/pulls/{int(implementation)}")
        if pr.get("state") == "open":
            return False

    source_issue = int(current.get("source_issue", 0))
    issue = _request("GET", f"/repos/{REPO}/issues/{source_issue}")
    labels = {str(item.get("name", "")) for item in issue.get("labels", [])}
    if "autonomy:human-hold" in labels:
        return True

    comments = _request(
        "GET",
        f"/repos/{REPO}/issues/{source_issue}/comments?per_page=100",
    )
    kilo_attempts = sum(
        "<!-- kilo-auto-repair:" in str(item.get("body", ""))
        for item in comments
    )
    return kilo_attempts >= 2


def transfer(
    new_issue: int,
    from_owner: str,
    to_owner: str,
    category: str,
    scope: str,
    source_sha: str,
) -> dict:
    fp = fingerprint(REPO, category, scope, source_sha)
    current = active_for_fingerprint(fp)
    if not current or current.get("owner") != from_owner:
        raise RuntimeError("active transfer source owner mismatch")
    if not previous_writer_inactive(current):
        raise RuntimeError("previous writer is still active")

    old_issue = int(current["source_issue"])
    released = {
        key: value
        for key, value in current.items()
        if key not in {"comment_id", "issue_url"}
    }
    released.update(
        {
            "status": "released",
            "reason": "ownership-transfer",
            "transfer_to": to_owner,
        }
    )
    post_state(old_issue, released)

    payload = {
        "version": 1,
        "status": "active",
        "fingerprint": fp,
        "owner": to_owner,
        "fence": uuid.uuid4().hex,
        "category": category,
        "scope": scope,
        "source_sha": source_sha,
        "source_issue": new_issue,
        "transferred_from_owner": from_owner,
        "transferred_from_issue": old_issue,
        "previous_fence": current.get("fence"),
    }
    return post_state(new_issue, payload)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    claim_cmd = sub.add_parser("claim")
    claim_cmd.add_argument("--issue", type=int, required=True)
    claim_cmd.add_argument("--owner", required=True)
    claim_cmd.add_argument("--category", required=True)
    claim_cmd.add_argument("--scope", required=True)
    claim_cmd.add_argument("--source-sha", required=True)

    bind_cmd = sub.add_parser("bind")
    bind_cmd.add_argument("--issue", type=int, required=True)
    bind_cmd.add_argument("--owner", required=True)
    bind_cmd.add_argument("--fingerprint", required=True)
    bind_cmd.add_argument("--implementation-pr", type=int, required=True)

    transfer_cmd = sub.add_parser("transfer")
    transfer_cmd.add_argument("--issue", type=int, required=True)
    transfer_cmd.add_argument("--from-owner", required=True)
    transfer_cmd.add_argument("--to-owner", required=True)
    transfer_cmd.add_argument("--category", required=True)
    transfer_cmd.add_argument("--scope", required=True)
    transfer_cmd.add_argument("--source-sha", required=True)

    release_cmd = sub.add_parser("release")
    release_cmd.add_argument("--issue", type=int, required=True)
    release_cmd.add_argument("--owner", required=True)
    release_cmd.add_argument("--fingerprint", required=True)
    release_cmd.add_argument("--reason", required=True)

    args = parser.parse_args()
    if args.cmd == "claim":
        result = claim(
            args.issue,
            args.owner,
            args.category,
            args.scope,
            args.source_sha,
        )
    elif args.cmd == "bind":
        result = bind(
            args.issue,
            args.owner,
            args.fingerprint,
            args.implementation_pr,
        )
    elif args.cmd == "transfer":
        result = transfer(
            args.issue,
            args.from_owner,
            args.to_owner,
            args.category,
            args.scope,
            args.source_sha,
        )
    else:
        result = release(
            args.issue,
            args.owner,
            args.fingerprint,
            args.reason,
        )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
