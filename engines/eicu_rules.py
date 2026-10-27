"""Review-only computational rules; no real-data extraction or production entry point."""
from __future__ import annotations
import argparse, csv, gzip, hashlib, json, math, platform, re, sqlite3, sys
from collections import Counter, defaultdict
from pathlib import Path


def norm(x): return " ".join((x or "").strip().casefold().split())

def integer(x): return int(x) if re.fullmatch(r"[+-]?\d+", (x or "").strip()) else None

def isadult(x):
    if re.sub(r"\s+", "", x or "") == ">89": return True
    a = integer(x)
    return a >= 18 if a is not None else None

def unit_value(row):
    def u(x): return re.sub(r"\s+", "", (x or "").strip().lower()).replace("µ", "u").replace("μ", "u")
    us = [u(row[k]) for k in ["labmeasurenamesystem", "labmeasurenameinterface"] if u(row[k])]
    if not us: return None, "unit_missing"
    if any(x not in {"mg/dl", "umol/l"} for x in us): return None, "unit_unrecognized"
    if len(set(us)) != 1: return None, "unit_conflict"
    if integer(row["labtypeid"]) != 1: return None, "not_confirmed_chemistry"
    try: v = float(row["labresult"])
    except (ValueError, TypeError): return None, "value_missing_or_nonnumeric"
    if not math.isfinite(v) or v <= 0: return None, "value_nonpositive_or_nonfinite"
    return (v / 88.4 if us[0] == "umol/l" else v), None

def versions_at_draw(rs):
    """Choose final available revision, preserving ties/invalid final records."""
    latest = max(r["revision"] for r in rs)
    last = [r for r in rs if r["revision"] == latest]
    vals = {r["value"] for r in last if r["value"] is not None}
    bad = any(r["value_issue"] is not None for r in last) or len(vals) != 1
    return {"draw": rs[0]["draw"], "revision": latest, "value": None if bad else next(iter(vals)), "unresolved": bad, "row_ids": [r["labid"] for r in last], "multiple_saved_revisions": len({r["revision"] for r in rs}) > 1}

def preserve_unordered_draw_groups(resolved, unordered):
    """Keep known collection groups uncertain when revision order is unknown.

    Draw-time equality is only a proxy. A later qualifying independent draw may
    still be chosen; an uncertain old draw does not globally invalidate it.
    """
    groups = {r["draw"]: dict(r) for r in resolved}
    for draw, rowids in unordered.items():
        g = groups.get(draw, {"draw": draw, "revision": None, "row_ids": [], "multiple_saved_revisions": False})
        g.update({"value": None, "unresolved": True, "version_order_unknown": True, "unordered_revision_row_ids": sorted(rowids)})
        groups[draw] = g
    return [groups[d] for d in sorted(groups)]

def unordered_draw_window(row, observation_end):
    if row["draw_time_unknown"] or not row["source_unit_collection_verified"] or row["time_issue"] not in {"missing_offset", "raw_zero_offset_uncertain", "revision_before_draw"}:
        return None
    if 0 < row["draw"] <= 360: return "early"
    if 360 < row["draw"] <= 1800 and row["draw"] < observation_end: return "future"
    return None
