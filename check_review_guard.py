from review_guard import install
install()
from pathlib import Path
import sqlite3
def blocked(call):
    try:
        call()
    except RuntimeError:
        return
    raise AssertionError('Expected synthetic review restriction')
blocked(lambda: sqlite3.connect(':memory:'))
blocked(lambda: (Path(__file__).parent.parent / 'outside_package_probe.txt').read_text())
blocked(lambda: (Path(__file__).parent / 'write_probe.txt').write_text('synthetic'))
assert not (Path(__file__).parent / 'write_probe.txt').exists()
print('SYNTHETIC_REVIEW_GUARD_CHECK_PASS')
