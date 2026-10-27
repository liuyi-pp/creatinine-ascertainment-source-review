"""No input argument and no database connection: synthetic rule checks only."""
from review_guard import install
install()
from engines import mimic_comparison, eicu_comparison
def main():
    mimic_comparison.tests()
    eicu_comparison.synthetic_tests()
    assert mimic_comparison._synthetic_reports['synthetic_verification.json']['patient_data_used'] is False
    assert eicu_comparison._synthetic_reports['synthetic_tests.json']['all_passed'] is True
    print('REVIEW_SYNTHETIC_RULE_CHECKS_PASS; NO_REAL_DATA_READ')
if __name__ == '__main__':
    main()
