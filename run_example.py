"""Use only the bundled invented examples; accepts no real-data input argument."""
from review_guard import install
install()
from pathlib import Path
import json
from datetime import timedelta
from engines import mimic_comparison as m, eicu_comparison as e
def main():
    obj = json.loads((Path(__file__).parent / 'examples' / 'synthetic_records.json').read_text())
    assert obj['synthetic_only'] and obj['not_sampled_from_database']
    for c in obj['cases']:
        r, f = c['reference'], c['future']
        if c['database'] == 'mimic':
            a = m.fake_record(r['draw_hours'], r['entry_hours'], r['value'])
            b = m.fake_record(f['draw_hours'], f['entry_hours'], f['value'], specimen='synthetic_future')
            origin = a['draw_t'] - timedelta(hours=r['draw_hours'])
            strict = m.reference_selection([a,b], origin, origin+timedelta(hours=6))
            relaxed = m.reference_selection([a,b], origin, origin+timedelta(hours=6), False)
            assert strict['value'] is None and relaxed['value'] is not None
        elif c['database'] == 'eicu':
            a = e.fixture_row(r['draw_minutes'], r['revision_minutes'], r['value'])
            b = e.fixture_row(f['draw_minutes'], f['revision_minutes'], f['value'], labid='synthetic_future')
            plan = e.fixture_plan()
            strict = e.case_state(plan, *e.grouped([a,b],plan))
            relaxed = e.case_state(plan, *e.grouped([a,b],plan,True))
            assert not strict['eligible_reference'] and relaxed['eligible_reference']
        else:
            raise ValueError('Unknown synthetic database fixture')
    print('BUNDLED_SYNTHETIC_EXAMPLES_PASS; NO_REAL_DATA_READ')
if __name__ == '__main__':
    main()
