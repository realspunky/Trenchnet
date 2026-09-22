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
 add(c,'A','A','A','maker','pumpfun'); add(c,'B','B','B','maker','embercurve'); add(c,'C','C','C','maker','pons'); add(c,'D','D','D','maker','pumpfun')
 r=process(c,1,now=1001,creator_limit=3); assert r['allowed']==3 and r['blocked']==1
 assert c.execute("select reason from global_filter_decisions where event_key like '%:d:launch'").fetchone()[0]=='creator_multi_launch'

def test_new_creator_not_penalized():
 c=db(); add(c,'A','Fresh','FRSH','newwallet')
 process(c,1,now=1001)
 assert c.execute('select allow from global_filter_decisions').fetchone()[0]==1


def test_stonk_holder_reward_policy_blocks_noneligible():
 c=db(); record(c,chain='solana',launchpad='stonk',address='S1',name='NoReward',symbol='NR',launched_at=1000,now=1000,metadata={'eligible':False,'rate':100,'reward_mint':'Q'})
 r=process(c,1,now=1001); assert r['blocked']==1
 assert c.execute("select reason from global_filter_decisions").fetchone()[0]=='holder_reward_policy'

def test_stonk_holder_reward_policy_allows_1_to_3_percent():
 for rate in (100,200,300):
  c=db(); record(c,chain='solana',launchpad='stonk',address='S'+str(rate),name='Reward'+str(rate),symbol='R'+str(rate),launched_at=1000,now=1000,metadata={'eligible':True,'rate':rate,'reward_mint':'Q'})
  r=process(c,1,now=1001); assert r['allowed']==1

def test_flap_holder_reward_policy_blocks_missing_rewards():
 c=db(); record(c,chain='bnb',launchpad='flap',address='0x'+'1'*40,name='Bad',symbol='BAD',launched_at=1000,now=1000,metadata={'verified':True,'token_tax_bps':300,'holder_rewards':False})
 r=process(c,1,now=1001); assert r['blocked']==1
 assert c.execute("select reason from global_filter_decisions").fetchone()[0]=='holder_reward_policy'


def test_holder_reward_alert_body_details():
 from global_filter import alert_body
 import json
 flap_meta=json.dumps({'verified':True,'token_tax_bps':300,'holder_rewards':True,'dividend_allocation_bps':8000,'reward_token':'0xReward'})
 row=('e','bnb','flap','0x'+'1'*40,'','Name','SYM','',1,85.0,0,'','',flap_meta)
 body=alert_body(row,{'creator_launches':1})
 assert 'Token tax: 3%' in body and 'Holder rewards: Enabled' in body and 'Reward asset: 0xReward' in body
 stonk_meta=json.dumps({'eligible':True,'rate':200,'reward_mint':'Q','reward_symbol':'CARDS'})
 row=('e','solana','stonk','Mint','','Name','SYM','',1,50.0,0,'','',stonk_meta)
 body=alert_body(row,{'creator_launches':1})
 assert 'Transfer tax: 2%' in body and 'Holder rewards: CARDS' in body
