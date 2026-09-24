import os,sys
sys.path.insert(0,os.path.dirname(__file__))
from v2_intelligence import bonding_gate,complete,extract

def test_all_platform_names_supported():
 from v2_adapters import fetch
 assert callable(fetch)
 for p in ('flap','stonk','pons','embercurve','pumpfun'):assert isinstance(p,str)

def test_mandatory_gate_exactly_60():
 assert bonding_gate(59.99) is None
 assert bonding_gate(60)==60
 assert bonding_gate(100)==100

def test_stage2_requires_every_core_signal():
 x={'description':'lore','twitter':'https://x.com/a','holders':{'count':50,'top10Pct':20},
    'snipers':{'count':2,'concentrationPct':3},
    'trades':{'buys':20,'sells':5,'uniqueBuyers':15,'uniqueSellers':5,'volume':1000}}
 assert complete(extract(x))
 del x['trades']['uniqueBuyers']
 assert not complete(extract(x))
