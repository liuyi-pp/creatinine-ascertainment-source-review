"""Review-only computational rules; no real-data extraction or production entry point."""
from pathlib import Path
from collections import Counter, defaultdict
from datetime import timedelta, datetime
from decimal import Decimal
import importlib.util, json, sqlite3, hashlib, sys, platform, traceback
from . import mimic_rules as a
_synthetic_reports = {}
def dump(name, obj):
    _synthetic_reports[name] = obj


def reference_selection(rs, t0, cut, availability_limit=True):
    """Exact prior reference semantics; comparison changes only entry upper bound."""
    early = [r for r in rs if r['draw_t'] is None or t0 <= r['draw_t'] <= cut]
    allowed = lambda r: not availability_limit or r['entry_t'] is None or r['entry_t'] <= cut
    earlysp = {(r['specimen'], r['itemid']) for r in early if allowed(r)}
    eligible, conflicts = a.specimen_versions(rs, cut if availability_limit else None)
    eligible = [r for r in eligible if t0 <= r['draw_t'] <= cut]
    conflicts = [sp for sp in conflicts if sp in earlysp]
    recent = max((r['draw_t'] for r in eligible), default=None)
    latest = [r for r in eligible if r['draw_t'] == recent] if recent else []
    values = {r['mgdl'] for r in latest}
    unresolved = [r['draw_t'] for r in early if r['draw_t'] is not None and
                  (r['specimen'], r['itemid']) in conflicts and allowed(r)]
    latest_unresolved = bool(unresolved and (recent is None or max(unresolved) >= recent))
    ref = next(iter(values)) if len(values) == 1 and not latest_unresolved else None
    return dict(value=ref, draw=recent, latest=latest, conflicts=conflicts,
                early=early, values=values, latest_unresolved=latest_unresolved)

def future_selection(rs, t0, end, untimed):
    cut = t0 + timedelta(hours=6)
    h30 = t0 + timedelta(hours=30)
    future = [r for r in rs if r['draw_t'] is None or
              (cut < r['draw_t'] <= h30 and r['draw_t'] < end)]
    futuresp = {(r['specimen'], r['itemid']) for r in future}
    frecs, conflicts = a.specimen_versions(rs)
    frecs = [r for r in frecs if cut < r['draw_t'] <= h30 and r['draw_t'] < end]
    conflicts = [sp for sp in conflicts if sp in futuresp]
    frecs, drawconflict = a.collapse_draws(frecs)
    return dict(records=frecs, version_conflicts=conflicts, draw_conflicts=drawconflict,
                bad=bool(conflicts) or bool(drawconflict) or untimed,
                terminal=any(t0 + timedelta(hours=24) < r['draw_t'] <= h30 for r in frecs),
                full_observation=end > h30, untimed=untimed)

def state_for(ref, fut, remove_full=False, remove_terminal=False, remove_any=False):
    if ref is None:
        return 'reference_unavailable_or_conflicting'
    if any(r['mgdl'] - ref >= Decimal('0.3') for r in fut['records']):
        return 'lab_only_event_preview'
    if fut.get('death_barrier', False):
        return 'lab_only_indeterminate_preview'
    full = remove_full or fut['full_observation']
    terminal = remove_terminal or fut['terminal']
    any_future = remove_any or bool(fut['records'])
    if full and terminal and any_future and not fut['bad']:
        return 'lab_only_rule_non_event_preview'
    return 'lab_only_indeterminate_preview'

def strict_record(e, rs, untimed):
    """Reproduce every stored old per-episode field, including legacy audit flags."""
    t0 = a.dt(e['origin']); end = a.dt(e['safe_end']); cut = t0 + timedelta(hours=6)
    sel = reference_selection(rs, t0, cut)
    fut = future_selection(rs, t0, end, untimed)
    death = a.dt(e.get('deathtime'))
    fut['death_barrier'] = bool(death and death <= t0 + timedelta(hours=30))
    reference = sel['value']; latest = sel['latest']; early = sel['early']
    state = state_for(reference, fut)
    # Preserve this legacy flag exactly for baseline reproduction. It is not used
    # as evidence for comparison two, which also requires identical itemid.
    overwritten = any(any(q['specimen'] == r['specimen'] and q['entry_t'] and
                          q['entry_t'] > cut and
                          (q['mgdl'] != r['mgdl'] or q['draw_t'] != r['draw_t'])
                          for q in rs) for r in latest)
    flags = {'reference_available': reference is not None,
             'unplaceable_collection_time_record': untimed,
             'early_invalid_or_conflicting_record': any(not r['valid'] for r in early) or bool(sel['conflicts']) or len(sel['values']) > 1,
             'early_draw_only_late_saved_version': any(r['valid'] and r['entry_t'] > cut for r in early),
             'selected_reference_specimen_has_later_different_value': overwritten,
             'future_valid_measurement': bool(fut['records']),
             'terminal_sample': fut['terminal'],
             'full_observation_to30h': fut['full_observation'],
             'future_invalid_or_conflicting_record': fut['bad'],
             'reference_without_any_future_valid_measurement': reference is not None and not fut['records'],
             'no_negative_without_reference': not (state == 'lab_only_rule_non_event_preview' and reference is None)}
    report = {'hadm_id': e['hadm_id'], 'subject_id': e['subject_id'], 'origin': e['origin'],
              'safe_end': e['safe_end'], 'age': e['age'], 'sex': e['sex'],
              'reference_mgdl': str(reference) if reference is not None else None,
              'reference_draw': sel['draw'], 'reference_lab_ids': [r['labid'] for r in latest],
              'reference_specimens': [r['specimen'] for r in latest],
              'reference_entry': [r['entry'] for r in latest], 'preview_state': state,
              'flags': flags, 'future_valid_draw_times': [r['draw'] for r in fut['records']],
              'future_valid_values': [str(r['mgdl']) for r in fut['records']],
              'first_qualifying_event_draw': min((r['draw_t'] for r in fut['records'] if reference is not None and r['mgdl'] - reference >= Decimal('0.3')), default=None),
              'RRT_status': 'not_integrated_unknown'}
    return report, sel, fut

def comparison_two(rs, sel, fut, cut):
    """Conservative unique specimen/item group; fixed strict reference object."""
    result = {'status': 'strict_reference_unavailable', 'comparable': False, 'unique_fixed_group': False,
              'later_saved_record_present': False, 'final_value': None,
              'value_changed': None, 'diagnostic_state': None}
    if sel['value'] is None:
        return result
    groups = {(r['specimen'], r['itemid']) for r in sel['latest']}
    if len(groups) != 1:
        result['status'] = 'multiple_equivalent_reference_groups_not_linked'
        return result
    group = next(iter(groups))
    result['unique_fixed_group'] = True
    saved = [r for r in rs if (r['specimen'], r['itemid']) == group]
    result['later_saved_record_present'] = any(r['entry_t'] and r['draw_t'] and r['draw_t'] <= r['entry_t'] and r['entry_t'] > cut for r in saved)
    if any(r['entry_t'] is None or r['draw_t'] is None or r['entry_t'] < r['draw_t'] for r in saved):
        result['status'] = 'saved_group_time_order_unresolved'
        return result
    final, conflicts = a.specimen_versions(saved)
    if conflicts or len(final) != 1:
        result['status'] = 'final_saved_group_invalid_or_conflicting'
        return result
    final = final[0]
    if final['draw_t'] != sel['draw']:
        result['status'] = 'saved_collection_time_changed_object_not_fixed'
        return result
    if not result['later_saved_record_present']:
        result['status'] = 'no_later_archived_comparison_opportunity'
        return result
    result.update(status='comparable_saved_group', comparable=True,
                  final_value=str(final['mgdl']), value_changed=not value_equal(final['mgdl'], sel['value']),
                  diagnostic_state=state_for(final['mgdl'], fut))
    return result

def fake_record(draw, entry, value, specimen='s', item='i', unit='mg/dL', labid='l'):
    t0 = datetime(2000, 1, 1)
    stamp = lambda h: str(t0 + timedelta(hours=h)) if h is not None else ''
    return a.normalize_records([('h', 'p', labid, specimen, item, stamp(draw), stamp(entry), str(value), unit, 'synthetic')])[0]

def tests():
    t0 = datetime(2000, 1, 1); cut = t0 + timedelta(hours=6); end = t0 + timedelta(hours=40)
    late = [fake_record(5, 7, '1')]
    assert reference_selection(late, t0, cut)['value'] is None
    assert reference_selection(late, t0, cut, False)['value'] == Decimal('1')
    missing = [fake_record(5, None, '1')]
    assert reference_selection(missing, t0, cut, False)['value'] is None
    reversed_time = [fake_record(5, 4, '1')]
    assert reference_selection(reversed_time, t0, cut, False)['value'] is None
    versions = [fake_record(5, 5.5, '1'), fake_record(5, 7, '1.2', labid='later')]
    assert reference_selection(versions, t0, cut)['value'] == Decimal('1')
    assert reference_selection(versions, t0, cut, False)['value'] == Decimal('1.2')
    changed_draw = [fake_record(5, 5.5, '1'), fake_record(8, 9, '1.2', labid='later')]
    assert reference_selection(changed_draw, t0, cut, False)['value'] is None
    bad_latest = [fake_record(5, 5.5, '1'), fake_record(5, 7, 'x', labid='later')]
    assert reference_selection(bad_latest, t0, cut, False)['value'] is None
    ties = [fake_record(5, 5.5, '1'), fake_record(5, 5.5, '1.1', labid='tie')]
    assert reference_selection(ties, t0, cut)['value'] is None
    different_item = [fake_record(5, 5.5, '1'), fake_record(5, 7, '1.9', item='other')]
    sel = reference_selection(different_item, t0, cut)
    fut = future_selection(different_item, t0, end, False)
    assert comparison_two(different_item, sel, fut, cut)['status'] == 'no_later_archived_comparison_opportunity'
    assert comparison_two(different_item, sel, fut, cut)['value_changed'] is None
    fut = future_selection([fake_record(8, 9, '1.3')], t0, end, False)
    assert state_for(Decimal('1'), fut) == 'lab_only_event_preview'
    assert state_for(Decimal('1.00001'), fut) == 'lab_only_indeterminate_preview'
    nofuture = future_selection([], t0, end, False)
    assert state_for(Decimal('1'), nofuture, remove_terminal=True) == 'lab_only_indeterminate_preview'
    assert state_for(Decimal('1'), nofuture, remove_any=True) == 'lab_only_indeterminate_preview'
    mid = future_selection([fake_record(8, 9, '1.1')], t0, end, False)
    assert state_for(Decimal('1'), mid, remove_terminal=True) == 'lab_only_rule_non_event_preview'
    early_end = future_selection([fake_record(25, 26, '1.1')], t0, t0 + timedelta(hours=27), False)
    assert state_for(Decimal('1'), early_end) == 'lab_only_indeterminate_preview'
    assert state_for(Decimal('1'), early_end, remove_full=True) == 'lab_only_rule_non_event_preview'
    invalid = future_selection([fake_record(25, 26, '1.1', unit='unknown')], t0, end, False)
    assert state_for(Decimal('1'), invalid) == 'lab_only_indeterminate_preview'
    at_end = future_selection([fake_record(30, 31, '1.3')], t0, t0 + timedelta(hours=30), False)
    assert not at_end['records']
    revised_future = [fake_record(8, 9, '1.3'), fake_record(35, 36, '1.3', labid='later')]
    assert not future_selection(revised_future, t0, end, False)['records']
    sel = reference_selection(versions, t0, cut)
    c2 = comparison_two(versions, sel, mid, cut)
    assert c2['comparable'] and c2['value_changed']
    assert comparison_two(changed_draw, reference_selection(changed_draw, t0, cut), mid, cut)['status'] == 'saved_collection_time_changed_object_not_fixed'
    invalid_old_time = [fake_record(5, 4, '1'), fake_record(5, 5.5, '1'), fake_record(5, 7, '1.1')]
    assert comparison_two(invalid_old_time, reference_selection(invalid_old_time, t0, cut), mid, cut)['status'] == 'saved_group_time_order_unresolved'
    invalid_old_value = [fake_record(5, 5.1, 'x'), fake_record(5, 5.5, '1'), fake_record(5, 7, '1.1')]
    assert comparison_two(invalid_old_value, reference_selection(invalid_old_value, t0, cut), mid, cut)['comparable']
    assert state_for(None, mid, remove_terminal=True) == 'reference_unavailable_or_conflicting'
    death_future = dict(early_end, death_barrier=True)
    assert state_for(Decimal('1'), death_future, remove_full=True) == 'lab_only_indeterminate_preview'
    death_event = dict(future_selection([fake_record(8, 9, '1.3')], t0, end, False), death_barrier=True)
    assert state_for(Decimal('1'), death_event, remove_full=True) == 'lab_only_event_preview'
    assert value_equal(Decimal('1'), Decimal('1.0000000001'))
    assert not value_equal(Decimal('1'), Decimal('1.00000001'))
    at24 = future_selection([fake_record(24, 25, '1.1')], t0, end, False)
    assert not at24['terminal']
    at30 = future_selection([fake_record(30, 31, '1.1')], t0, end, False)
    assert at30['terminal']
    dump('synthetic_verification.json', {'all_synthetic_boundary_checks_passed': True,
         'patient_data_used': False, 'entry_upper_bound_only_relaxed_in_comparison_one': True,
         'invalid_latest_no_fallback': True, 'comparison_two_same_item_required': True,
         'no_negative_without_future_sample': True, 'future_saved_collection_reposition_respected': True})
    print('MIMIC synthetic boundary checks passed; no patient data used.')

def compact_reference(sel):
    return {'available': sel['value'] is not None, 'value_mgdl': str(sel['value']) if sel['value'] is not None else None,
            'draw': sel['draw'], 'lab_ids': [r['labid'] for r in sel['latest']],
            'specimen_item_keys': [[r['specimen'], r['itemid']] for r in sel['latest']]}

def value_equal(left, right):
    return abs(left - right) <= Decimal('1e-9')

def reference_transition(strict, relaxed):
    if strict['value'] is None and relaxed['value'] is None:
        return 'unavailable_under_both'
    if strict['value'] is None:
        return 'new_reference_after_relaxing_entry_limit'
    if relaxed['value'] is None:
        return 'strict_reference_lost_after_final_saved_selection'
    draw = strict['draw'] != relaxed['draw']
    value = not value_equal(strict['value'], relaxed['value'])
    if draw:
        return 'both_available_different_draw_' + ('different_value' if value else 'same_value')
    return 'both_available_same_draw_' + ('different_value' if value else 'same_value')
