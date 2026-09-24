import os, sqlite3, sys, time
sys.path.insert(0,os.path.dirname(__file__))
from v2_intelligence import *
os.environ['TRENCHNET_V2_ENABLED']='true'

def db():
    c=sqlite3.connect(":memory:");setup(c);return c

def full():
    return {"description":"real lore","twitter":"https://x.com/a",
      "holders":{"count":100,"top10Pct":20,"devPct":1},
      "snipers":{"count":3,"concentrationPct":4,"largestPct":2,"stillHolding":2,"sold":1},
      "trades":{"buys":50,"sells":20,"uniqueBuyers":40,"uniqueSellers":18,
                "buyVolume":8000,"sellVolume":3000,"volume":11000,"windowSeconds":3600}}

def test_60_is_absolute():
    assert bonding_gate(59.999,False) is None
    assert bonding_gate(60,False)==60
    assert bonding_gate(.60,False)==60

def test_incomplete_stage2_never_ready():
    c=db(); e="solana:stonk:x:launch"
    mark_progress(c,e,"x","stonk",95,int(time.time())-10)
    assert not upsert_intelligence(c,e,"x","stonk",{"description":"x","twitter":"https://x.com/x"})
    assert gate(c,e,95)[0] is False

def test_complete_stage2_ready():
    c=db(); e="solana:stonk:x:launch"
    mark_progress(c,e,"x","stonk",95,int(time.time())-10)
    assert upsert_intelligence(c,e,"x","stonk",full())
    assert gate(c,e,95)==(True,"v2_ready")
