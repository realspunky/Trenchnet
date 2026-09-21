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


def test_every_launchpad_preference_is_independent(monkeypatch):
 from alert_preferences import set_all,toggle,LAUNCHPADS
 monkeypatch.setenv('PUBLIC_ALERTS_ENABLED','true'); monkeypatch.delenv('ADMIN_CHAT_ID',raising=False)
 for selected in LAUNCHPADS:
  c=db(); c.execute('INSERT INTO users(id) VALUES(1)'); ensure_user(c,1); set_all(c,1,False); toggle(c,1,selected)
  chain={'flap':'bnb','pons':'robinhood'}.get(selected,'solana')
  for i,pad in enumerate(LAUNCHPADS):
   ch={'flap':'bnb','pons':'robinhood'}.get(pad,'solana')
   record(c,chain=ch,launchpad=pad,address=f'{pad}{i}',name=f'N{i}',symbol=f'S{i}',creator=f'C{i}',now=1000+i)
  filter_process(c,0,now=1010)
  process(c,now=1011)
  pads=[r[0] for r in c.execute("SELECT u.launchpad FROM global_outbox o JOIN unified_launches u ON u.event_key=o.event_key WHERE o.state='pending'").fetchall()]
  assert pads==[selected]

def test_preference_change_blocks_already_queued_alert(monkeypatch):
 from alert_preferences import set_all,toggle
 from alert_router import enforce_preferences
 c=db(); c.execute('INSERT INTO users(id) VALUES(1)'); ensure_user(c,1)
 monkeypatch.setenv('PUBLIC_ALERTS_ENABLED','true'); monkeypatch.delenv('ADMIN_CHAT_ID',raising=False)
 set_all(c,1,False); toggle(c,1,'flap')
 record(c,chain='bnb',launchpad='flap',address='FLAP1',name='F',symbol='F',creator='C',now=1000)
 filter_process(c,0,now=1001); process(c,now=1002)
 assert c.execute("SELECT state FROM global_outbox").fetchone()[0]=='pending'
 set_all(c,1,False); toggle(c,1,'pumpfun')
 assert enforce_preferences(c)==1
 assert c.execute("SELECT state FROM global_outbox").fetchone()[0]=='preference_blocked'
