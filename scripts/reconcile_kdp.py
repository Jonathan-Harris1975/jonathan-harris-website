#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv
from collections import defaultdict
from pathlib import Path

FUNNEL_FIELDS=('qualified_sessions','book_views','amazon_clicks')

def number(value:str, field:str, line:int)->int:
    text=str(value or '').strip()
    if text=='': return 0
    try: n=int(text)
    except ValueError as exc: raise ValueError(f'line {line}: {field} must be an integer') from exc
    if n<0: raise ValueError(f'line {line}: {field} cannot be negative')
    return n

def read_funnel(path:Path):
    out=defaultdict(lambda:{k:0 for k in FUNNEL_FIELDS})
    with path.open(newline='',encoding='utf-8-sig') as f:
        reader=csv.DictReader(f); required={'date','book_slug',*FUNNEL_FIELDS}
        if not reader.fieldnames or not required.issubset(reader.fieldnames): raise ValueError(f'{path}: expected columns {sorted(required)}')
        for line,row in enumerate(reader,2):
            key=((row.get('date') or '').strip(),(row.get('book_slug') or '').strip())
            if not all(key): raise ValueError(f'line {line}: date and book_slug are required')
            for field in FUNNEL_FIELDS: out[key][field]+=number(row.get(field,''),field,line)
    return out

def read_sales(path:Path):
    out=defaultdict(int)
    with path.open(newline='',encoding='utf-8-sig') as f:
        reader=csv.DictReader(f); required={'date','book_slug','sales'}
        if not reader.fieldnames or not required.issubset(reader.fieldnames): raise ValueError(f'{path}: expected columns {sorted(required)}')
        for line,row in enumerate(reader,2):
            key=((row.get('date') or '').strip(),(row.get('book_slug') or '').strip())
            if not all(key): raise ValueError(f'line {line}: date and book_slug are required')
            out[key]+=number(row.get('sales',''),'sales',line)
    return out

def rate(num:int,den:int)->str:
    return '' if den<=0 else f'{num/den:.6f}'

def reconcile(funnel:Path,sales:Path,output:Path)->None:
    f=read_funnel(funnel); s=read_sales(sales); keys=sorted(set(f)|set(s))
    fields=['date','book_slug','qualified_sessions','book_views','amazon_clicks','sales','book_reach','amazon_click_rate','outbound_to_sale_conversion']
    with output.open('w',newline='',encoding='utf-8') as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader()
        for key in keys:
            m=f.get(key,{k:0 for k in FUNNEL_FIELDS}); sales_count=s.get(key,0)
            w.writerow({
                'date': key[0],
                'book_slug': key[1],
                **m,
                'sales': sales_count,
                'book_reach': rate(m['book_views'], m['qualified_sessions']),
                'amazon_click_rate': rate(m['amazon_clicks'], m['book_views']),
                'outbound_to_sale_conversion': rate(sales_count, m['amazon_clicks']),
            })

def main()->int:
    ap=argparse.ArgumentParser(description='Reconcile website funnel metrics with real KDP daily sales exports.')
    ap.add_argument('--funnel',required=True,type=Path);ap.add_argument('--sales',required=True,type=Path);ap.add_argument('--output',required=True,type=Path);args=ap.parse_args()
    try: reconcile(args.funnel,args.sales,args.output)
    except (OSError,ValueError) as exc: ap.error(str(exc))
    return 0
if __name__=='__main__': raise SystemExit(main())
