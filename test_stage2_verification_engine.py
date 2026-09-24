import sqlite3
from v2_intelligence import setup,mark_progress,upsert_intelligence

def db():
 c=sqlite3.connect(':memory:'); setup(c); return c

def test_zero_metrics_are_verified():
 c=db(); mark_progress(c,'e','a','pons',65,now=100)
 m={'description':'real','social_checked':True,'holders':{'count':1,'top10Pct':10},'snipers':{'count':0,'concentrationPct':0},'trades':{'buys':0,'sells':0,'uniqueBuyers':0,'uniqueSellers':0,'volume':0}}
 assert upsert_intelligence(c,'e','a','pons',m,now=101)
 assert c.execute("select state from v2_intelligence where event_key='e'").fetchone()[0]=='ready'

def test_error_is_not_unavailable():
 c=db(); mark_progress(c,'e','a','embercurve',65,now=100)
 m={'description':'real','social_checked':True,'holders':{'count':1,'top10Pct':10},'native_chain_error':'RPCError'}
 assert not upsert_intelligence(c,'e','a','embercurve',m,now=101)
 assert c.execute("select status from v2_collector_state where event_key='e' and collector='trading'").fetchone()[0]=='error'

def test_explicit_unavailable_can_complete_profile():
 c=db(); mark_progress(c,'e','a','embercurve',65,now=100)
 m={'description':'real','social_checked':True,'holders':{'count':1,'top10Pct':10},'trading_unavailable':'verified source exposes no trade history','snipers_unavailable':'cannot verify early wallets'}
 assert upsert_intelligence(c,'e','a','embercurve',m,now=101)
