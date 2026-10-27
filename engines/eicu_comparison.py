"""Review-only computational rules; no real-data extraction or production entry point."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, math, platform, re, sqlite3, sys
from collections import Counter, defaultdict
from pathlib import Path
from . import eicu_rules as old
CONTROLS = {"C_terminal_removed": "terminal_valid_draw", "C_continuous_removed": "continuous_observation"}
COMMON = {"indeterminate_reference": "reference_indeterminate", "lab_event_preliminary": "observed_rise", "lab_rule_nonevent_preliminary": "no_rise_under_rule", "diagnostic_rule_nonevent_only": "no_rise_under_rule", "indeterminate_future": "followup_indeterminate"}
ROOT = Path('.')
_synthetic_reports = {}
def save(path, obj):
    # Tests report to memory; never write into an archived data directory.
    _synthetic_reports[Path(path).name] = obj
def sha(path):
    # Used by inherited tests to fingerprint this cleaned source only.
    if Path(path).resolve() != Path(__file__).resolve():
        raise ValueError('Review runner permits hashing its own module only')
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def grouped(rs, p, relax_saved_cutoff=False):
    early = defaultdict(list); future = defaultdict(list)
    early_unordered = defaultdict(list); future_unordered = defaultdict(list)
    flags = Counter(); ambiguous_future_time = False
    for r in rs:
        if r["time_issue"]:
            flags[r["time_issue"]] += 1
            uw = old.unordered_draw_window(r, p["observation_end"])
            if uw == "early":
                early_unordered[r["draw"]].append(r["labid"])
                flags["early_draw_version_order_uncertain"] += 1
            elif uw == "future":
                future_unordered[r["draw"]].append(r["labid"])
                flags["future_draw_version_order_uncertain"] += 1
            if ((r["draw_time_unknown"] and r["source_unit_intersects_future_window"])
                or (not r["draw_time_unknown"] and 360 < r["draw"] <= 1800)):
                ambiguous_future_time = True
            continue
        d, rev = r["draw"], r["revision"]
        if 0 < d <= rev and d <= 360 and (relax_saved_cutoff or rev <= 360):
            early[d].append(r)
        if 0 < d <= 360 and rev > 360: flags["prelandmark_draw_revised_after_landmark"] += 1
        if 360 < d <= 1800 and d < p["observation_end"]: future[d].append(r)
        if r["value_issue"]: flags[r["value_issue"]] += 1
    ev = old.preserve_unordered_draw_groups([old.versions_at_draw(v) for _, v in sorted(early.items())], early_unordered)
    fv = old.preserve_unordered_draw_groups([old.versions_at_draw(v) for _, v in sorted(future.items())], future_unordered)
    return ev, fv, flags, ambiguous_future_time

def case_state(p, ev, fv, flags, ambiguous):
    ref = ev[-1] if ev else None
    reference_ok = ref is not None and not ref["unresolved"]
    future_conflict = any(v["unresolved"] for v in fv)
    finalvals = [v for v in fv if not v["unresolved"]]
    event = reference_ok and any(v["value"] >= ref["value"] + 0.3 - 1e-9 for v in finalvals)
    terminal = any(1440 < v["draw"] <= 1800 for v in finalvals)
    coverage = p["observation_end"] > 1800
    death_by_end = p["death_offset"] is not None and p["death_offset"] <= 1800
    if not reference_ok:
        state = "indeterminate_reference"
        reason = "latest_known_candidate_draw_unresolved" if ref else "no_eligible_saved_reference"
    elif event:
        state, reason = "lab_event_preliminary", "observed_threshold_crossing"
    elif coverage and terminal and not future_conflict and not ambiguous and not death_by_end and not p["death_time_uncertain"]:
        state, reason = "lab_rule_nonevent_preliminary", "prespecified_observation_rule_met"
    else:
        state = "indeterminate_future"
        reason = "death_time_uncertain" if p["death_time_uncertain"] else "recorded_death_by_horizon" if death_by_end else "observation_ends_by_horizon" if not coverage else "future_time_or_version_unresolved" if future_conflict or ambiguous else "no_terminal_window_valid_draw"
    return {"hospital_stay_id": p["hospital_stay_id"], "first_unit_id": p["first_unit_id"], "hospitalid": p["hospitalid"], "uniquepid": p["uniquepid"], "state": state, "reason": reason, "reference": ref, "eligible_reference": reference_ok, "future_valid_draws": len(finalvals), "terminal_window_valid_draw": terminal, "observation_covers_horizon": coverage, "death_by_horizon": death_by_end, "death_time_uncertain": p["death_time_uncertain"], "future_version_or_value_conflict": future_conflict, "ambiguous_future_time": ambiguous, "all_flags": dict(flags), "rrt_status_merged": False, "final_clinical_label": False}

def reference_signature(q):
    if not q["eligible_reference"]: return None
    r = q["reference"]
    return r["draw"], r["value"]

def same_value(a, b): return math.isclose(a, b, rel_tol=0.0, abs_tol=1e-9)

def compare_availability(strict, relaxed):
    a, b = reference_signature(strict), reference_signature(relaxed)
    status = ("new_reference_assigned" if a is None and b is not None else
              "reference_became_indeterminate" if a is not None and b is None else
              "both_indeterminate" if a is None and b is None else
              "both_available_value_changed" if not same_value(a[1], b[1]) else
              "both_available_draw_changed_only" if a[0] != b[0] else "both_available_same_draw_value")
    return {"diagnostic_control_only": True, "reference_comparison": status, "draw_changed_when_both_available": bool(a is not None and b is not None and a[0] != b[0]), "value_changed_when_both_available": bool(a is not None and b is not None and not same_value(a[1], b[1])), "strict_state": strict["state"], "diagnostic_state": relaxed["state"], "strict_common_state": COMMON[strict["state"]], "diagnostic_common_state": COMMON[relaxed["state"]], "strict_reference": strict["reference"], "diagnostic_reference": relaxed["reference"]}

def compare_versions(strict, rs):
    result = {"diagnostic_control_only": True, "status": "strict_reference_unavailable", "strict_reference_available": strict["eligible_reference"], "uniquely_linked_group": False, "later_saved_comparison_opportunity": None, "comparable_pair": False, "proxy_only": True, "real_specimen_link_confirmed": False, "changed": None}
    if not strict["eligible_reference"]: return result
    ref = strict["reference"]
    group = [r for r in rs if r["draw"] == ref["draw"]]
    if (not group or any(not r["source_unit_collection_verified"] for r in group)
        or len({r["patientunitstayid"] for r in group}) != 1
        or len({old.integer(r["labresultoffset"]) for r in group}) != 1
        or len({old.norm(r["labname"]) for r in group}) != 1
        or len({old.integer(r["labtypeid"]) for r in group}) != 1):
        result["status"] = "proxy_group_not_comparable"
        return result
    result["uniquely_linked_group"] = True
    known_later = any(not r["time_issue"] and r["revision"] > 360 for r in group)
    result["later_saved_comparison_opportunity"] = True if known_later else None if any(r["time_issue"] for r in group) else False
    if any(r["time_issue"] for r in group):
        result["status"] = "proxy_group_saved_order_unresolved"
        return result
    if not result["later_saved_comparison_opportunity"]:
        result["status"] = "no_later_archived_comparison_opportunity"
        return result
    final = old.versions_at_draw(group)
    if final["unresolved"]:
        result["status"] = "final_proxy_group_unresolved"
        return result
    result.update({"status": "comparable_draw_time_proxy", "comparable_pair": True, "changed": not same_value(ref["value"], final["value"]), "strict_draw": ref["draw"], "strict_saved_revision": ref["revision"], "final_saved_revision": final["revision"], "strict_value": ref["value"], "final_value": final["value"], "final_minus_strict": final["value"] - ref["value"], "final_after_landmark": final["revision"] > 360})
    return result

def requirement_map(q):
    return {"continuous_observation": q["observation_covers_horizon"], "any_future_valid_draw": q["future_valid_draws"] > 0, "terminal_valid_draw": q["terminal_window_valid_draw"], "no_death_by_horizon": not q["death_by_horizon"] and not q["death_time_uncertain"], "future_time_version_resolved": not q["future_version_or_value_conflict"] and not q["ambiguous_future_time"]}

def compare_observation(q):
    req = requirement_map(q)
    controls = {}
    for arm, drop in CONTROLS.items():
        if q["state"] in {"indeterminate_reference", "lab_event_preliminary"}:
            state = q["state"]
        elif all(v for k, v in req.items() if k != drop):
            state = "diagnostic_rule_nonevent_only"
        else:
            state = "indeterminate_future"
        controls[arm] = {"diagnostic_control_only": True, "diagnostic_state": state, "strict_common_state": COMMON[q["state"]], "diagnostic_common_state": COMMON[state], "strict_indeterminate_assigned_nonevent": q["state"] == "indeterminate_future" and state == "diagnostic_rule_nonevent_only"}
    reasons = {"continuous_observation_insufficient": not req["continuous_observation"], "no_future_valid_draw": not req["any_future_valid_draw"], "no_terminal_valid_draw": not req["terminal_valid_draw"], "recorded_death_by_horizon": q["death_by_horizon"], "death_time_uncertain": q["death_time_uncertain"], "future_time_unresolved": q["ambiguous_future_time"], "future_version_or_value_unresolved": q["future_version_or_value_conflict"]}
    return {"diagnostic_control_only": True, "requirements_met": req, "overlapping_reason_flags": reasons, "single_requirement_removal": controls}

def fixture_row(draw=100, rev=120, value=1.0, uid="synthetic_unit", labid="synthetic_lab", issue=None, value_issue=None):
    return {"labid": labid, "patientunitstayid": uid, "labresultoffset": str(draw), "labresultrevisedoffset": str(rev), "labname": "creatinine", "labtypeid": "1", "labmeasurenamesystem": "mg/dL", "labmeasurenameinterface": "mg/dL", "draw": draw, "revision": rev, "value": value, "value_issue": value_issue, "time_issue": issue, "draw_time_unknown": draw in {None, 0}, "source_unit_intersects_future_window": True, "source_unit_collection_verified": draw is not None and draw != 0}

def fixture_plan(end=2000, death=None):
    return {"hospital_stay_id": "synthetic_stay", "first_unit_id": "synthetic_unit", "hospitalid": "synthetic_hospital", "uniquepid": "synthetic_person", "observation_end": end, "death_offset": death, "death_time_uncertain": False}

def synthetic_tests():
    tests = {}
    p = fixture_plan()
    def qs(rs, relax=False, plan=p): return case_state(plan, *grouped(rs, plan, relax))
    future = fixture_row(1500, 1520, 1.1, labid="synthetic_future")
    late = fixture_row(100, 400, 1.0)
    tests["late_saved_early_draw_not_strict_reference"] = not qs([late, future])["eligible_reference"] and qs([late, future], True)["eligible_reference"]
    tests["fixed_source_identifiers_under_reference_control"] = all(qs([late, future])[k] == qs([late, future], True)[k] for k in ("hospital_stay_id", "first_unit_id", "hospitalid", "uniquepid"))
    early = fixture_row(100, 120, 1.0, labid="synthetic_early")
    corrected = fixture_row(100, 500, 1.4, labid="synthetic_corrected")
    a, b = qs([early, corrected, future]), qs([early, corrected, future], True)
    tests["saved_version_filter_precedes_version_selection"] = a["reference"]["value"] == 1.0 and b["reference"]["value"] == 1.4
    tests["fixed_proxy_nested_version_comparison"] = compare_versions(a, [early, corrected, future])["changed"] is True
    unknown = fixture_row(100, 0, 1.2, labid="synthetic_unknown", issue="raw_zero_offset_uncertain")
    tests["unordered_same_draw_blocks_both_rules"] = not qs([early, unknown])["eligible_reference"] and not qs([early, unknown], True)["eligible_reference"]
    tie = fixture_row(100, 120, 1.2, labid="synthetic_tie")
    tests["conflicting_latest_saved_tie_stays_unknown"] = not qs([early, tie])["eligible_reference"]
    threshold = fixture_row(400, 410, 1.3, labid="synthetic_threshold")
    tests["threshold_inclusive"] = qs([early, threshold])["state"] == "lab_event_preliminary"
    before = fixture_row(300, 400, 2.0, labid="synthetic_early_late")
    tests["late_report_of_early_collection_is_not_future_event"] = qs([early, before])["state"] == "indeterminate_future"
    tests["no_future_lab_does_not_become_nonevent"] = qs([early])["state"] == "indeterminate_future"
    q = qs([early, future], plan=fixture_plan(1700))
    tests["early_observation_end_only_relaxed_diagnostically"] = q["state"] == "indeterminate_future" and compare_observation(q)["single_requirement_removal"]["C_continuous_removed"]["strict_indeterminate_assigned_nonevent"]
    q = qs([early, fixture_row(500, 510, 1.1, labid="synthetic_mid")])
    tests["single_terminal_requirement_drop"] = compare_observation(q)["single_requirement_removal"]["C_terminal_removed"]["strict_indeterminate_assigned_nonevent"]
    req = requirement_map(qs([early]))
    tests["dropping_any_future_with_terminal_kept_cannot_fill_unknown_synthetic_only"] = not all(v for k, v in req.items() if k != "any_future_valid_draw")
    badfuture = fixture_row(1600, 1610, None, labid="synthetic_bad_future", value_issue="unit_unrecognized")
    q = qs([early, future, badfuture])
    tests["invalid_future_prevents_nonevent"] = q["state"] == "indeterminate_future"
    tests["independent_valid_event_survives_other_future_conflict"] = qs([early, threshold, badfuture])["state"] == "lab_event_preliminary"
    tests["strict_unavailable_never_enters_version_subset"] = compare_versions(qs([late]), [late])["status"] == "strict_reference_unavailable"
    tests["single_saved_record_not_version_change_evidence"] = compare_versions(qs([early]), [early])["status"] == "no_later_archived_comparison_opportunity"
    q = qs([early, future], plan=fixture_plan(1700, 1700))
    tests["death_barrier_is_never_relaxed"] = not any(v["strict_indeterminate_assigned_nonevent"] for v in compare_observation(q)["single_requirement_removal"].values())
    tests["reference_unavailable_immune_to_future_rule_removal"] = all(x["diagnostic_state"] == "indeterminate_reference" for x in compare_observation(qs([late]))["single_requirement_removal"].values())
    invalidfinal = fixture_row(100, 500, None, labid="synthetic_invalid_final", value_issue="unit_unrecognized")
    tests["A_can_lose_reference_after_final_invalid_state"] = qs([early])["eligible_reference"] and not qs([early, invalidfinal], True)["eligible_reference"]
    tests["B_invalid_final_is_noncomparable"] = compare_versions(qs([early, invalidfinal]), [early, invalidfinal])["status"] == "final_proxy_group_unresolved"
    tests["B_unordered_saved_record_is_noncomparable"] = compare_versions(qs([early]), [early, unknown])["status"] == "proxy_group_saved_order_unresolved"
    proxy_unknown = compare_versions(qs([early]), [early, corrected, unknown])
    tests["B_known_later_opportunity_retained_but_order_uncertainty_blocks_pair"] = proxy_unknown["later_saved_comparison_opportunity"] is True and not proxy_unknown["comparable_pair"]
    priorinvalid = fixture_row(100, 110, None, labid="synthetic_prior_invalid", value_issue="value_missing_or_nonnumeric")
    tests["B_unselected_prior_invalid_value_does_not_block_valid_endpoints"] = compare_versions(qs([priorinvalid, early, corrected]), [priorinvalid, early, corrected])["comparable_pair"]
    earlyrevision = fixture_row(100, 200, 1.1, labid="synthetic_second_early")
    tests["B_multiple_early_revisions_without_later_opportunity_not_paired"] = compare_versions(qs([early, earlyrevision]), [early, earlyrevision])["status"] == "no_later_archived_comparison_opportunity"
    tests["paired_value_roundoff_tolerance"] = same_value(1.0, 1.0 + 1e-10) and not same_value(1.0, 1.0 + 1e-8)
    at24 = fixture_row(1440, 1450, 1.1, labid="synthetic_at24")
    at30 = fixture_row(1800, 1810, 1.1, labid="synthetic_at30")
    tests["24_hour_draw_not_terminal"] = not qs([early, at24])["terminal_window_valid_draw"]
    tests["30_hour_draw_terminal_only_before_observation_end"] = qs([early, at30])["terminal_window_valid_draw"] and not qs([early, at30], plan=fixture_plan(1800))["terminal_window_valid_draw"]
    evq = qs([early, threshold, badfuture])
    savedq = json.dumps(evq, sort_keys=True)
    tests["C_event_invariance"] = all(x["diagnostic_state"] == "lab_event_preliminary" for x in compare_observation(evq)["single_requirement_removal"].values())
    tests["C_strict_reference_and_case_immutable"] = json.dumps(evq, sort_keys=True) == savedq
    tests["C_no_future_valid_measurement_stays_unknown"] = all(x["diagnostic_state"] == "indeterminate_future" for x in compare_observation(qs([early]))["single_requirement_removal"].values())
    overlap = compare_observation(qs([early], plan=fixture_plan(1000)))["overlapping_reason_flags"]
    tests["overlapping_reasons_retained_not_forced_disjoint"] = overlap["continuous_observation_insufficient"] and overlap["no_future_valid_draw"] and overlap["no_terminal_valid_draw"]
    save(ROOT / "synthetic_tests.json", {"all_passed": all(tests.values()), "tests": tests, "script_sha256": sha(Path(__file__))})
    if not all(tests.values()): raise AssertionError("Synthetic comparison tests failed")
    print("synthetic_tests_passed=true; patient_cache_read=false", flush=True)
