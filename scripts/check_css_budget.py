#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CSS_DIR=ROOT/'assets'/'css'
REPORT=ROOT/'css-size-report.json'
CONFIG=ROOT/'config'/'css-budget.json'

def compact_size(text:str)->int:
    # Reporting only. This never rewrites production CSS.
    no_comments=re.sub(r'/\*.*?\*/','',text,flags=re.S)
    compact=re.sub(r'\s+',' ',no_comments)
    compact=re.sub(r'\s*([{}:;,>])\s*',r'\1',compact).strip()
    return len(compact.encode('utf-8'))

def report_rows():
    rows=[]
    for path in sorted(CSS_DIR.glob('*.css')):
        raw=path.read_text(encoding='utf-8')
        original=len(raw.encode('utf-8')); mini=compact_size(raw)
        rows.append({
            'file': str(path.relative_to(ROOT)),
            'original_bytes': original,
            'minified_bytes': mini,
            'reduction_bytes': original - mini,
            'reduction_pct': round(((original - mini) / original * 100), 2) if original else 0.0,
        })
    return rows

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--write',action='store_true'); ap.add_argument('--check',action='store_true'); args=ap.parse_args()
    rows=report_rows()
    if args.write: REPORT.write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8')
    cfg=json.loads(CONFIG.read_text(encoding='utf-8')) if CONFIG.exists() else {}
    site=next((x for x in rows if x['file']=='assets/css/site.css'),None)
    if not site: print('ERROR: assets/css/site.css missing',file=sys.stderr); return 1
    maximum=int(cfg.get('site_css_max_bytes') or 0)
    if args.check:
        if not REPORT.exists(): print('ERROR: css-size-report.json missing',file=sys.stderr); return 1
        stored=json.loads(REPORT.read_text(encoding='utf-8'))
        stored_site=next((x for x in stored if x.get('file')=='assets/css/site.css'),None)
        if not stored_site or stored_site.get('original_bytes')!=site['original_bytes']:
            print('ERROR: css-size-report.json is stale; run scripts/check_css_budget.py --write',file=sys.stderr); return 1
        if maximum and site['original_bytes']>maximum:
            print(f"ERROR: site.css is {site['original_bytes']} bytes; budget is {maximum}",file=sys.stderr); return 1
    print(f"site.css: {site['original_bytes']} bytes (budget {maximum or 'not set'})")
    return 0
if __name__=='__main__': raise SystemExit(main())
