"""Additional invented checks of documented method boundaries; no external input."""
from review_guard import install
install()
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from engines import mimic_comparison as m, eicu_comparison as e

LANDMARK=6
TERMINAL_LOWER=24
HORIZON=30

def mimic_checks():
    ref = m.fake_record(2, 2, '1.1')
    origin = ref['draw_t'] - timedelta(hours=2)
    cut, end = origin+timedelta(hours=LANDMARK), origin+timedelta(hours=HORIZON+2)
    future = m.fake_record(HORIZON-1, HORIZON-1, '1.2', specimen='synthetic_future')
    missing = m.future_selection([], origin, end, False)
    assert m.state_for(Decimal('1.1'), missing, remove_terminal=True) == 'lab_only_indeterminate_preview'
    assert m.state_for(Decimal('1.1'), missing, remove_full=True) == 'lab_only_indeterminate_preview'
    terminal_boundary = m.future_selection([m.fake_record(TERMINAL_LOWER,TERMINAL_LOWER,'1.2')], origin,end,False)
    assert not terminal_boundary['terminal']
    horizon = m.fake_record(HORIZON,HORIZON,'1.2',specimen='synthetic_horizon')
    assert not m.future_selection([horizon],origin,origin+timedelta(hours=HORIZON),False)['records']
    assert m.future_selection([horizon],origin,end,False)['terminal']
    lower = m.fake_record(HORIZON-1,HORIZON-1,'0.2',specimen='synthetic_later_minimum')
    early = m.reference_selection([ref,lower],origin,cut)
    assert early['value'] == Decimal('1.1')
    fut = m.future_selection([future],origin,end,False)
    snapshot = deepcopy(fut)
    m.state_for(early['value'],fut,remove_terminal=True)
    m.state_for(early['value'],fut,remove_full=True)
    assert fut == snapshot
    no_opportunity = m.comparison_two([ref], m.reference_selection([ref],origin,cut),fut,cut)
    assert no_opportunity['value_changed'] is None and not no_opportunity['comparable']

def eicu_checks():
    p=e.fixture_plan((HORIZON+2)*60)
    ref=e.fixture_row(120,120,1.1)
    future=e.fixture_row((HORIZON-1)*60,(HORIZON-1)*60,1.2,labid='synthetic_future')
    def state(rows,plan=p,relax=False):
        return e.case_state(plan,*e.grouped(rows,plan,relax))
    no_future=state([ref])
    assert all(x['diagnostic_state']=='indeterminate_future' for x in e.compare_observation(no_future)['single_requirement_removal'].values())
    terminal=e.fixture_row(TERMINAL_LOWER*60,TERMINAL_LOWER*60,1.2,labid='synthetic_terminal_boundary')
    assert not state([ref,terminal])['terminal_window_valid_draw']
    horizon=e.fixture_row(HORIZON*60,HORIZON*60,1.2,labid='synthetic_horizon')
    assert not state([ref,horizon],e.fixture_plan(HORIZON*60))['terminal_window_valid_draw']
    lower=e.fixture_row((HORIZON-1)*60,(HORIZON-1)*60,0.2,labid='synthetic_later_minimum')
    assert state([ref,lower])['reference']['value']==1.1
    zero=e.fixture_row(0,120,1.1,issue='raw_zero_offset_uncertain')
    assert not state([zero,future])['eligible_reference']
    q=state([ref,future]);snap=deepcopy(q)
    e.compare_observation(q)
    assert q==snap
    dead=state([ref,future],e.fixture_plan((HORIZON+2)*60,HORIZON*60-30))
    assert not any(x['strict_indeterminate_assigned_nonevent'] for x in e.compare_observation(dead)['single_requirement_removal'].values())

if __name__=='__main__':
    mimic_checks();eicu_checks()
    print('DOCUMENTED_METHOD_BOUNDARIES_CHECK_PASS; SYNTHETIC_INPUTS_ONLY')
