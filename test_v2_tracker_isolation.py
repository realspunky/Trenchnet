import sqlite3, os
os.environ['TRENCHNET_V2_ENABLED']='true'
from launch_model import setup as launch_setup, record
import v2_tracker

def test_adapter_failure_does_not_abort_batch(monkeypatch):
    c=sqlite3.connect(':memory:'); launch_setup(c)
    e=record(c,chain='solana',launchpad='pumpfun',address='mintx',name='x',symbol='x',now=100,launched_at=100)
    c.execute("UPDATE unified_launches SET pipeline_state='v2_tracking' WHERE event_key=?",(e,));c.commit()
    monkeypatch.setattr(v2_tracker,'adapter_fetch',lambda *a: (_ for _ in ()).throw(RuntimeError('429')))
    r=v2_tracker.cycle(c,now=101)
    assert r['processed']==1 and r['waiting']==1
