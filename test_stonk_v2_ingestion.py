import sqlite3, time
import stonk
from launch_model import setup as unified_setup
from v2_intelligence import setup as v2_setup

MINT='11111111111111111111111111111111'

def _db():
    c=sqlite3.connect(':memory:')
    c.execute('CREATE TABLE users(id INTEGER PRIMARY KEY,threshold REAL)')
    c.execute('INSERT INTO users VALUES(1,80)')
    stonk.setup(c); unified_setup(c); v2_setup(c)
    return c

def test_raw_stonk_detection_enters_v2_before_metadata(monkeypatch):
    monkeypatch.setenv('TRENCHNET_V2_ENABLED','true')
    c=_db(); now=time.time()
    c.execute('INSERT INTO stonk_cursor VALUES(1,?,?)',(now-10,now-100)); c.commit()
    calls=[]
    def fake(path, now=None):
        calls.append(path)
        if path.startswith('/launches?'):
            return ({'launches':[{'mint':MINT,'createdAt':'2026-09-24T15:00:00+00:00'}],
                     'pagination':{'totalPages':1,'page':1}}, time.time())
        raise stonk.FeedError('metadata unavailable')
    # Use a launch timestamp relative to the scanner clock to satisfy its active window.
    import datetime
    created=datetime.datetime.fromtimestamp(now-1,datetime.timezone.utc).isoformat()
    def fake2(path, now=None):
        if path.startswith('/launches?'):
            return ({'launches':[{'mint':MINT,'createdAt':created}],
                     'pagination':{'totalPages':1,'page':1}}, time.time())
        raise stonk.FeedError('metadata unavailable')
    s=stonk.Scanner(c,1,get=fake2)
    s.scan()
    u=c.execute("SELECT launchpad,address,bonding_progress,pipeline_state FROM unified_launches WHERE address=?",(MINT,)).fetchone()
    assert u==('stonk',MINT,None,'v2_tracking')
    v=c.execute("SELECT state,crossed_90_at FROM v2_intelligence WHERE address=?",(MINT,)).fetchone()
    assert v==('tracking',None)

def test_stonk_normalize_converts_source_fraction_to_canonical_percent():
    data={'network':'mainnet-beta','token':{'mint':MINT,'graduationProgress':0.42,'status':'new',
          'launchpad':'launchlab','mode':'reward','transferFee':{'bps':200},
          'quote':{'mint':MINT,'symbol':'SOL'},'name':'Test','symbol':'TST'}}
    s=stonk.normalize(data,MINT)
    assert s['progress']==42.0
    assert s['eligible'] is True
