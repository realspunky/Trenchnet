import sqlite3
from launch_model import record,setup as model_setup
from global_filter import setup,process

def db():
 c=sqlite3.connect(':memory:'); model_setup(c); setup(c); return c

def add(c,address,name='DOG',symbol='DOG',creator='alice',pad='pumpfun',now=1000):
 return record(c,chain='solana',launchpad=pad,address=address,name=name,symbol=symbol,creator=creator,launched_at=now,now=now)

def test_duplicate_across_launchpads_is_filtered():
 c=db(); add(c,'A',pad='pumpfun'); add(c,'B',pad='embercurve')
 r=process(c,1,now=1001); assert r=={'processed':2,'allowed':1,'blocked':1}
 assert c.execute("select pipeline_state from unified_launches where address='B'").fetchone()[0]=='filtered'
 assert c.execute('select count(*) from global_outbox').fetchone()[0]==0  # routing is a separate stage

def test_creator_limit_is_global_across_launchpads():
 c=db()
 add(c,'A','A','A','maker','pumpfun'); add(c,'B','B','B','maker','embercurve'); add(c,'C','C','C','maker','stonk'); add(c,'D','D','D','maker','pumpfun')
 r=process(c,1,now=1001,creator_limit=3); assert r['allowed']==3 and r['blocked']==1
 assert c.execute("select reason from global_filter_decisions where event_key like '%:d:launch'").fetchone()[0]=='creator_multi_launch'

def test_new_creator_not_penalized():
 c=db(); add(c,'A','Fresh','FRSH','newwallet')
 process(c,1,now=1001)
 assert c.execute('select allow from global_filter_decisions').fetchone()[0]==1
