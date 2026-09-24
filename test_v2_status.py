import os, sqlite3, time
import bot
from v2_intelligence import setup


def db():
    c=sqlite3.connect(':memory:')
    c.execute('CREATE TABLE users(id INTEGER PRIMARY KEY, threshold INTEGER NOT NULL DEFAULT 80)')
    c.execute('CREATE TABLE state(key TEXT PRIMARY KEY,value INTEGER)')
    c.execute('CREATE TABLE global_outbox(id INTEGER PRIMARY KEY,state TEXT)')
    setup(c)
    now=int(time.time())
    c.execute('CREATE TABLE v2_health(id INTEGER PRIMARY KEY,updated INTEGER,message TEXT)')
    c.execute("INSERT INTO v2_health VALUES(1,?,'ok')",(now,))
    c.execute('CREATE TABLE pons_health(id INTEGER PRIMARY KEY,updated INTEGER,status TEXT)')
    c.execute("INSERT INTO pons_health VALUES(1,?,'ok')",(now,))
    c.execute("""INSERT INTO v2_intelligence(event_key,address,launchpad,crossed_90_at,updated_at,state,description,social_checked)
                 VALUES('x','a','pons',?,?, 'awaiting_intelligence','token',1)""",(now,now))
    c.commit();return c

def test_v2_status_is_not_v1_status(monkeypatch):
    c=db(); monkeypatch.setenv('TRENCHNET_V2_ENABLED','true'); monkeypatch.setenv('ADMIN_CHAT_ID','1')
    out=bot.reply(c,1,'/status')
    assert 'TRENCHNET V2 — PRIVATE TEST' in out
    assert 'Bonding gate: ≥90% mandatory' in out
    assert 'PILOT DELIVERIES' not in out.upper()
    assert 'Access:' not in out and 'Expiry:' not in out
    assert 'PONS' in out and 'Awaiting intel: 1' in out
    assert 'Missing:' in out

def test_v2_status_admin_only(monkeypatch):
    c=db(); monkeypatch.setenv('TRENCHNET_V2_ENABLED','true'); monkeypatch.setenv('ADMIN_CHAT_ID','1')
    assert bot.reply(c,2,'/status')=='Use /help to see available commands.'

def test_v2_removes_trial_keyboard_source():
    src=open('bot.py').read()
    assert "TRENCHNET_V2_ENABLED" in src and "'remove_keyboard': True" in src
