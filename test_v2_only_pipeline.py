import os, sqlite3, time
from launch_model import record
from v2_intelligence import setup as v2_setup, mark_progress
from v2_qualification import process as qualify

def db():
    c=sqlite3.connect(':memory:')
    v2_setup(c)
    return c

def test_all_launchpads_enter_tracking_below_60(monkeypatch):
    monkeypatch.setenv('TRENCHNET_V2_ENABLED','true')
    for pad,chain in [('flap','bnb'),('stonk','solana'),('pons','robinhood'),('embercurve','solana'),('pumpfun','solana')]:
        c=db();key=record(c,chain=chain,launchpad=pad,address='test-'+pad,
                         bonding_progress=0.98,metadata={'name':'Test'},now=int(time.time()))
        assert c.execute('SELECT pipeline_state FROM unified_launches WHERE event_key=?',(key,)).fetchone()[0]=='v2_tracking'
        assert c.execute('SELECT crossed_90_at FROM v2_intelligence WHERE event_key=?',(key,)).fetchone()[0] is None

def test_v2_qualification_rejects_below_60_even_with_stage2_bypass(monkeypatch):
    monkeypatch.setenv('TRENCHNET_V2_ENABLED','true');monkeypatch.setenv('STAGE2_REQUIRED','false')
    c=db();key=record(c,chain='robinhood',launchpad='pons',address='test-low',bonding_progress=0.98,now=int(time.time()))
    with c:c.execute("UPDATE unified_launches SET pipeline_state='intake' WHERE event_key=?",(key,))
    qualify(c)
    assert c.execute('SELECT pipeline_state FROM unified_launches WHERE event_key=?',(key,)).fetchone()[0]=='v2_tracking'

def test_v2_qualification_allows_verified_crossing(monkeypatch):
    monkeypatch.setenv('TRENCHNET_V2_ENABLED','true');monkeypatch.setenv('STAGE2_REQUIRED','false')
    c=db();now=int(time.time())
    key=record(c,chain='robinhood',launchpad='pons',address='test-high',bonding_progress=60.0,now=now)
    with c:c.execute("UPDATE unified_launches SET pipeline_state='intake' WHERE event_key=?",(key,))
    qualify(c,now=now)
    assert c.execute('SELECT pipeline_state FROM unified_launches WHERE event_key=?',(key,)).fetchone()[0]=='approved'

def test_reward_policy_v2_only(monkeypatch):
    from v2_qualification import holder_reward_policy
    assert holder_reward_policy('flap',{'verified':True,'holder_rewards':True,'token_tax_bps':100})
    assert not holder_reward_policy('flap',{'verified':True,'holder_rewards':False,'token_tax_bps':100})
    assert holder_reward_policy('stonk',{'eligible':True,'rate':200,'reward_mint':'abc'})
    assert not holder_reward_policy('stonk',{'eligible':False,'rate':200,'reward_mint':'abc'})
