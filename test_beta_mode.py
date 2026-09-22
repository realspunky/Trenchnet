import os, sqlite3
from unittest.mock import patch
import bot, alert_router

def db():
    c=sqlite3.connect(':memory:'); bot.setup(c); bot.alert_pref_setup(c)
    c.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, threshold INTEGER NOT NULL DEFAULT 80 CHECK(threshold BETWEEN 80 AND 95))'); c.execute('CREATE TABLE state (key TEXT PRIMARY KEY,value INTEGER)'); c.commit(); return c

def test_beta_hides_status_and_price_but_admin_keeps_status():
    c=db()
    with patch.dict(os.environ,{'BETA_TESTING_ENABLED':'true','ADMIN_CHAT_ID':'1'},clear=False):
        assert bot.reply(c,2,'/status')=='Use /help to see available commands.'
        assert bot.reply(c,2,'/price')=='Use /help to see available commands.'
        assert bot.reply(c,2,'/plans')=='Use /help to see available commands.'
        assert 'Bonding threshold' in bot.reply(c,1,'/status')

def test_beta_help_has_no_status_price_or_trial():
    c=db()
    with patch.dict(os.environ,{'BETA_TESTING_ENABLED':'true'},clear=False):
        text=bot.reply(c,2,'/start')
        assert '/alerts' in text and '/status' not in text and '/price' not in text and '/trial' not in text
        assert 'No trial limit' in bot.reply(c,2,'/trial')

def test_beta_recipients_all_registered_users():
    c=db(); c.execute('INSERT INTO users(id) VALUES(2)'); c.execute('INSERT INTO users(id) VALUES(3)'); c.commit()
    with patch.dict(os.environ,{'BETA_TESTING_ENABLED':'true','PUBLIC_ALERTS_ENABLED':'false','ADMIN_CHAT_ID':'1'},clear=False):
        assert alert_router.recipients(c)==[1,2,3]
