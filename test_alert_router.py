import os,sqlite3
from launch_model import setup as model_setup,record
from global_filter import setup as filter_setup,process as filter_process
from alert_router import setup,process
from alert_preferences import ensure_user,toggle

def db():
 c=sqlite3.connect(':memory:'); c.execute('CREATE TABLE users(id INTEGER PRIMARY KEY, threshold INTEGER DEFAULT 80)'); model_setup(c);filter_setup(c);setup(c);return c

def test_router_respects_launchpad_selection(monkeypatch):
 c=db(); c.execute('INSERT INTO users(id) VALUES(1)'); ensure_user(c,1); toggle(c,1,'pumpfun')
 monkeypatch.setenv('PUBLIC_ALERTS_ENABLED','true'); monkeypatch.delenv('ADMIN_CHAT_ID',raising=False)
 record(c,chain='solana',launchpad='pumpfun',address='A',name='A',symbol='A',creator='x',now=1000)
 record(c,chain='solana',launchpad='embercurve',address='B',name='B',symbol='B',creator='y',now=1001)
 filter_process(c,0,now=1002)
 r=process(c,now=1003); assert r=={'processed':2,'queued':1}
 assert c.execute('SELECT event_key FROM global_outbox').fetchone()[0].startswith('solana:embercurve:')
