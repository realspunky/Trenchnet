import sqlite3
from launch_model import setup,record,social_links
from global_filter import alert_body
from scanner import alert_payload

def test_social_normalization_and_persistence():
 c=sqlite3.connect(':memory:'); setup(c)
 record(c,chain='solana',launchpad='pumpfun',address='Mint123',metadata={'twitter':'https://x.com/token','website':'https://token.example'})
 r=c.execute('select social_x_url,website_url from unified_launches').fetchone()
 assert r==('https://x.com/token','https://token.example')

def test_reject_fake_x_host():
 assert social_links({'twitter':'https://evil.example/x.com/foo'})[0]==''

def test_alert_buttons():
 row=('k','solana','pumpfun','11111111111111111111111111111111','','Token','TOK','',1,None,0,'https://x.com/token','https://token.example')
 body=alert_body(row,{'creator_launches':1})
 p=alert_payload(1,body)
 b=p['reply_markup']['inline_keyboard'][0]
 assert [x['text'] for x in b]==['📋 Copy contract','𝕏 X','🌐 Website']

def test_nested_pump_metadata_links():
 x,w=social_links({'uri':'ipfs://x','metadata':{'twitter':'https://twitter.com/token','website':'https://token.example'}})
 assert x=='https://twitter.com/token' and w=='https://token.example'
