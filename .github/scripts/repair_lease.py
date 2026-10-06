#!/usr/bin/env python3
"""Durable single-writer ownership leases stored on real GitHub issues/PRs."""
from __future__ import annotations
import argparse, hashlib, json, os, urllib.request, urllib.error, uuid
from typing import Any

API="https://api.github.com"
REPO=os.environ.get("REPO") or os.environ.get("GITHUB_REPOSITORY","")
TOKEN=os.environ.get("GH_TOKEN","")
MARKER="<!-- autonomy-lease:v1 "

def fingerprint(repository:str, category:str, scope:str, source_sha:str)->str:
    raw=json.dumps([repository,category,scope,source_sha],separators=(",",":"),ensure_ascii=True)
    return hashlib.sha256(raw.encode()).hexdigest()

def marker_payload(body:str)->dict[str,Any]|None:
    if MARKER not in body: return None
    try:
        raw=body.split(MARKER,1)[1].split(" -->",1)[0]
        data=json.loads(raw)
    except Exception:
        return None
    return data if data.get("version")==1 and data.get("fingerprint") else None

def _request(method:str,path:str,data:dict|None=None):
    req=urllib.request.Request(API+path,data=None if data is None else json.dumps(data).encode(),method=method)
    req.add_header("Accept","application/vnd.github+json")
    req.add_header("Authorization",f"Bearer {TOKEN}")
    req.add_header("X-GitHub-Api-Version","2022-11-28")
    if data is not None: req.add_header("Content-Type","application/json")
    try:
        with urllib.request.urlopen(req,timeout=30) as r:
            raw=r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GitHub API HTTP {e.code}: {e.read().decode()[:300]}") from e

def all_lease_comments()->list[dict]:
    out=[]
    for page in range(1,11):
        rows=_request("GET",f"/repos/{REPO}/issues/comments?per_page=100&page={page}")
        out.extend(rows)
        if len(rows)<100: break
    return [c for c in out if marker_payload(c.get("body",""))]

def active_for_fingerprint(fp:str)->dict|None:
    state=None
    for c in sorted(all_lease_comments(),key=lambda x:int(x["id"])):
        p=marker_payload(c.get("body",""))
        if p and p.get("fingerprint")==fp:
            state={**p,"comment_id":c["id"],"issue_url":c.get("issue_url")}
    return state if state and state.get("status")=="active" else None

def post_state(issue:int,payload:dict)->dict:
    body=MARKER+json.dumps(payload,separators=(",",":"),sort_keys=True)+" -->"
    _request("POST",f"/repos/{REPO}/issues/{issue}/comments",{"body":body})
    return payload

def claim(issue:int, owner:str, category:str, scope:str, source_sha:str)->dict:
    fp=fingerprint(REPO,category,scope,source_sha)
    current=active_for_fingerprint(fp)
    if current:
        if current.get("owner")!=owner:
            raise RuntimeError(f"fingerprint already owned by {current.get('owner')}")
        return current
    payload={"version":1,"status":"active","fingerprint":fp,"owner":owner,"fence":uuid.uuid4().hex,
             "category":category,"scope":scope,"source_sha":source_sha,"source_issue":issue}
    return post_state(issue,payload)

def bind(issue:int, owner:str, fp:str, implementation_pr:int)->dict:
    current=active_for_fingerprint(fp)
    if not current or current.get("owner")!=owner:
        raise RuntimeError("active lease owner mismatch")
    payload={k:v for k,v in current.items() if k not in {"comment_id","issue_url"}}
    payload["implementation_pr"]=implementation_pr
    return post_state(issue,payload)

def release(issue:int, owner:str, fp:str, reason:str)->dict:
    current=active_for_fingerprint(fp)
    if not current or current.get("owner")!=owner:
        raise RuntimeError("active lease owner mismatch")
    payload={k:v for k,v in current.items() if k not in {"comment_id","issue_url"}}
    payload.update({"status":"released","reason":reason})
    return post_state(issue,payload)

def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="cmd",required=True)
    c=sub.add_parser("claim"); c.add_argument("--issue",type=int,required=True); c.add_argument("--owner",required=True); c.add_argument("--category",required=True); c.add_argument("--scope",required=True); c.add_argument("--source-sha",required=True)
    b=sub.add_parser("bind"); b.add_argument("--issue",type=int,required=True); b.add_argument("--owner",required=True); b.add_argument("--fingerprint",required=True); b.add_argument("--implementation-pr",type=int,required=True)
    r=sub.add_parser("release"); r.add_argument("--issue",type=int,required=True); r.add_argument("--owner",required=True); r.add_argument("--fingerprint",required=True); r.add_argument("--reason",required=True)
    a=p.parse_args()
    if a.cmd=="claim": out=claim(a.issue,a.owner,a.category,a.scope,a.source_sha)
    elif a.cmd=="bind": out=bind(a.issue,a.owner,a.fingerprint,a.implementation_pr)
    else: out=release(a.issue,a.owner,a.fingerprint,a.reason)
    print(json.dumps(out,sort_keys=True))
if __name__=="__main__": main()
