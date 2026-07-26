#!/usr/bin/env python3
"""Fail the build when core brand text/background pairs fall below WCAG AA."""
from __future__ import annotations

def rgb(hex_value: str):
    h=hex_value.lstrip('#')
    return tuple(int(h[i:i+2],16)/255 for i in (0,2,4))

def lin(c: float) -> float:
    return c/12.92 if c <= 0.04045 else ((c+0.055)/1.055)**2.4

def lum(hex_value: str) -> float:
    r,g,b=rgb(hex_value)
    return .2126*lin(r)+.7152*lin(g)+.0722*lin(b)

def ratio(fg: str,bg: str) -> float:
    a,b=sorted((lum(fg),lum(bg)),reverse=True)
    return (a+.05)/(b+.05)

PAIRS={
    'footer body':('#E2E8F0','#0D1420',4.5),
    'footer labels':('#CBD5E1','#0D1420',4.5),
    'footer links':('#DBEAFE','#0D1420',4.5),
    'hero lead':('#D1D5DB','#0D1420',4.5),
    'body text':('#374151','#FFFFFF',4.5),
    'muted text':('#4B5563','#FFFFFF',4.5),
    'primary button':('#FFFFFF','#4F46E5',4.5),
}

def main():
    failed=[]
    for name,(fg,bg,minimum) in PAIRS.items():
        value=ratio(fg,bg)
        print(f'{name}: {value:.2f}:1')
        if value < minimum: failed.append((name,value,minimum))
    if failed:
        for name,value,minimum in failed: print(f'[FAIL] {name}: {value:.2f}:1 < {minimum}:1')
        return 1
    print('Core colour contrast contract passed.')
    return 0
if __name__=='__main__': raise SystemExit(main())
