"""Single Railway service: command bot plus optional private scanner."""
import os
import signal
import subprocess
import sys
import time

if __name__=='__main__':
    children=[subprocess.Popen([sys.executable,'-u','bot.py'])]
    if os.environ.get('GLOBAL_FILTER_ENABLED','true')=='true':
        children.append(subprocess.Popen([sys.executable,'-u','global_filter.py']))
        children.append(subprocess.Popen([sys.executable,'-u','alert_router.py']))
    if os.environ.get('SCANNER_ENABLED')=='true':
        children.append(subprocess.Popen([sys.executable,'-u','scanner.py']))
    if os.environ.get('STONK_ENABLED')=='true':
        children.append(subprocess.Popen([sys.executable,'-u','stonk.py']))
    if os.environ.get('PONS_ENABLED')=='true':
        children.append(subprocess.Popen([sys.executable,'-u','pons.py']))
    if os.environ.get('EMBER_ENABLED')=='true':
        children.append(subprocess.Popen([sys.executable,'-u','ember.py']))
    if os.environ.get('PUMPFUN_ENABLED')=='true':
        children.append(subprocess.Popen([sys.executable,'-u','pumpfun.py']))
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
