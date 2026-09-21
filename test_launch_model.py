import sqlite3
from launch_model import setup,record

def db():
 c=sqlite3.connect(':memory:');setup(c);return c

def test_record_is_idempotent_and_updates_lifecycle():
 c=db(); k=record(c,chain='solana',launchpad='pumpfun',address='Mint1',name='A',symbol='A',creator='C',launched_at=10,now=11)
 assert k=='solana:pumpfun:mint1:launch'
 record(c,chain='solana',launchpad='pumpfun',address='Mint1',name='A',symbol='A',creator='C',launched_at=10,bonding_progress=82.5,migrated=True,now=20)
 r=c.execute('select count(*),bonding_progress,migrated,last_seen from unified_launches').fetchone()
 assert r==(1,82.5,1,20)

def test_same_address_different_launchpads_are_distinct():
 c=db()
 record(c,chain='solana',launchpad='stonk',address='X',now=1)
 record(c,chain='solana',launchpad='embercurve',address='X',now=1)
 assert c.execute('select count(*) from unified_launches').fetchone()[0]==2

def test_rejects_unknown_source():
 c=db()
 try:record(c,chain='solana',launchpad='wat',address='X')
 except ValueError:return
 assert False
