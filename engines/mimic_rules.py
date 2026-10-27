"""Review-only computational rules; no real-data extraction or production entry point."""
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import csv, gzip, json, re, sqlite3, hashlib, sys, uuid, platform, time, math
import importlib.util


def dt(v):
    try:return datetime.fromisoformat(v)
    except (ValueError,TypeError):return None

def num(v):
    try:
        x=Decimal(v)
        return x if x.is_finite() else None
    except (InvalidOperation,TypeError):return None

def mgdl(value,unit):
    x=num(value)
    if x is None or x<=0:return None
    u=unit.strip().casefold().replace('μ','u').replace('µ','u').replace(' ','')
    if u in {'mg/dl'}:return x
    if u in {'umol/l'}:return x/Decimal('88.4')
    return None

def normalize_records(records):
    result=[]
    for x in records:
        d=dict(zip(['hadm','subject','labid','specimen','itemid','draw','entry','value','unit','linkmode'],x))
        d['draw_t']=dt(d['draw']);d['entry_t']=dt(d['entry']);d['mgdl']=mgdl(d['value'],d['unit'])
        d['valid']=d['draw_t'] is not None and d['entry_t'] is not None and d['draw_t']<=d['entry_t'] and d['mgdl'] is not None and bool(d['specimen'])
        result.append(d)
    return result

def specimen_versions(records,cutoff=None):
    groups=defaultdict(list)
    for r in records:
        if cutoff is None or r['entry_t'] is None or r['entry_t']<=cutoff:groups[(r['specimen'],r['itemid'])].append(r)
    selected=[];conflicts=[]
    for sp,rs in groups.items():
        if not sp[0] or any(r['entry_t'] is None for r in rs):conflicts.append(sp);continue
        latest=max(r['entry_t'] for r in rs);same=[r for r in rs if r['entry_t']==latest]
        if any(not r['valid'] for r in same) or len({(r['draw_t'],r['mgdl']) for r in same})!=1:conflicts.append(sp)
        else:selected.append(same[0])
    return selected,conflicts

def collapse_draws(records):
    groups=defaultdict(list)
    for r in records:groups[r['draw_t']].append(r)
    result=[];conflicts=[]
    for draw,rs in groups.items():
        if len({r['mgdl'] for r in rs})!=1:conflicts.append(draw)
        else:result.append(rs[0])
    return result,conflicts
