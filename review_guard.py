"""Audit guard for the synthetic-only review entry points; not a security sandbox."""
import sys
from pathlib import Path
def install():
    root = Path(__file__).resolve().parent
    runtime = Path(sys.base_prefix).resolve()
    sys.dont_write_bytecode = True
    def guard(event, args):
        if event in {'sqlite3.connect', 'socket.connect', 'subprocess.Popen'}:
            raise RuntimeError('Synthetic review entry point blocks databases, network and subprocesses')
        if event == 'open' and not isinstance(args[0], int):
            path = Path(args[0]).resolve()
            mode = args[1]
            if isinstance(mode, str) and any(c in mode for c in 'wax+'):
                raise RuntimeError('Synthetic review entry point does not write files')
            if not (path.is_relative_to(root) or path.is_relative_to(runtime)):
                raise RuntimeError('Read outside review package and Python runtime blocked')
    sys.addaudithook(guard)
