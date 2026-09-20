"""Single Railway service: command bot plus optional private scanner."""
import os
import signal
import subprocess
import sys
import time

if __name__=='__main__':
    children=[subprocess.Popen([sys.executable,'-u','bot.py'])]
    if os.environ.get('SCANNER_ENABLED')=='true':
        children.append(subprocess.Popen([sys.executable,'-u','scanner.py']))
    if os.environ.get('STONK_ENABLED')=='true':
        children.append(subprocess.Popen([sys.executable,'-u','stonk.py']))
    def stop(signum, frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while all(p.poll() is None for p in children):time.sleep(1)
    finally:
        for p in children:
            if p.poll() is None:p.terminate()
        for p in children:
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill();p.wait()
    sys.exit(1)
