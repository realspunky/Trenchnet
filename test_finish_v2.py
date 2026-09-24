import os, sqlite3
os.environ['TRENCHNET_V2_ENABLED']='true'
from v2_intelligence import complete, extract, bonding_gate

def test_core_readiness_does_not_fabricate_unique_traders():
    m={'description':'x','social_checked':True,'holders':{'count':10,'top10Pct':30},'snipers':{'count':2,'concentrationPct':4},'trades':{'buys':5,'sells':2,'uniqueBuyers':4,'uniqueSellers':2,'volume':100}}
    assert complete(extract(m))

def test_missing_volume_still_blocks():
    m={'description':'x','social_checked':True,'holders':{'count':10,'top10Pct':30},'snipers':{'count':2,'concentrationPct':4},'trades':{'buys':5,'sells':2,'uniqueBuyers':4,'uniqueSellers':2}}
    assert not complete(extract(m))

def test_90_gate_exact():
    assert bonding_gate(89.999) is None
    assert bonding_gate(90)==90
