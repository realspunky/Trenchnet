import sqlite3, json
from launch_model import setup as launch_setup, record
from v2_intelligence import setup as v2_setup, mark_progress
import v2_tracker

def test_awaiting_rows_are_not_starved_by_tracking_batch(monkeypatch):
    c=sqlite3.connect(':memory:');launch_setup(c);v2_setup(c)
    # 300 fresh trackers exceed the normal 250 batch.
    for i in range(300):
        record(c,chain='robinhood',launchpad='pons',address=f'0x{i:040x}',name='x',symbol='x',now=1000+i)
        ek=c.execute('select event_key from unified_launches where address=?',(f'0x{i:040x}',)).fetchone()[0]
        c.execute("update unified_launches set pipeline_state='v2_tracking',last_seen=? where event_key=?",(2000+i,ek))
    ek=c.execute('select event_key from unified_launches limit 1').fetchone()[0]
    c.execute("update unified_launches set pipeline_state='awaiting_intelligence' where event_key=?",(ek,))
    mark_progress(c,ek,c.execute('select address from unified_launches where event_key=?',(ek,)).fetchone()[0],'pons',95,1000,False,2900)
    seen=[]
    def fake(c,row,now):seen.append(row[0]);return False
    monkeypatch.setattr(v2_tracker,'refresh_from_stored',fake)
    v2_tracker.cycle(c,now=3001,limit=250)
    assert ek in seen
