from pons_v2_intelligence import _holder_stats

def test_holder_concentration_and_dev():
    hs=_holder_stats([
      {'address':{'hash':'0x'+'1'*40},'value':'50'},
      {'address':{'hash':'0x'+'2'*40},'value':'30'},
      {'address':{'hash':'0x'+'3'*40},'value':'20'},
    ],'0x'+'2'*40)
    assert hs['count']==3
    assert hs['top10Pct']==100
    assert hs['devPct']==30

def test_trade_decoder_preserves_zero_metrics(monkeypatch):
    # Extraction must treat valid zeros as data, not as missing values.
    from v2_intelligence import extract, complete
    x=extract({'description':'real lore','social_checked':True,'holders':{'count':10,'top10Pct':50},
               'snipers':{'count':0,'concentrationPct':0},
               'trades':{'buys':4,'sells':0,'uniqueBuyers':3,'uniqueSellers':0,'volume':1.2},
               'volume_asset':'ETH'})
    assert x['sniper_count']==0 and x['sniper_concentration_pct']==0
    assert x['sell_count']==0 and x['unique_sellers']==0
    assert x['volume_asset']=='ETH' and complete(x)
