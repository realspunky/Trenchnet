import os,sqlite3
import alert_router
from v2_intelligence import setup as v2setup

def db():
 c=sqlite3.connect(':memory:')
 c.execute('CREATE TABLE users(id INTEGER PRIMARY KEY,threshold INTEGER DEFAULT 80,created INTEGER DEFAULT 0)')
 c.execute('INSERT INTO users(id) VALUES(1)')
 c.execute('''CREATE TABLE unified_launches(id INTEGER PRIMARY KEY,event_key TEXT UNIQUE,chain TEXT,launchpad TEXT,address TEXT,creator TEXT,name TEXT,symbol TEXT,pair_symbol TEXT,source_tx TEXT,source_height INTEGER,launched_at INTEGER,first_seen INTEGER,last_seen INTEGER,bonding_progress REAL,migrated INTEGER,source_table TEXT,metadata TEXT,social_x_url TEXT DEFAULT '',website_url TEXT DEFAULT '',pipeline_state TEXT DEFAULT 'intake')''')
 alert_router.setup(c);v2setup(c);return c

def test_pending_alert_rechecked_and_blocked_under_90(monkeypatch):
 monkeypatch.setenv('TRENCHNET_V2_ENABLED','true')
 c=db();c.execute("INSERT INTO unified_launches(event_key,chain,launchpad,address,name,symbol,bonding_progress,migrated,metadata) VALUES('e','solana','pumpfun','m','N','N',89,0,'{}')")
 c.execute("INSERT INTO global_outbox(recipient,event_key,body,state,expires) VALUES(1,'e','x','pending',9999999999)");c.commit()
 alert_router.enforce_preferences(c)
 assert c.execute("SELECT state FROM global_outbox WHERE event_key='e'").fetchone()[0]=='v2_blocked'
