from binance_v2_intelligence import normalize

def test_binance_normalize_verified_fields_only():
    meta={'description':'cat lore','twitter':'https://x.com/cat','website':'https://cat.test','creatorAddress':'DEV'}
    dyn={'holders':'123','top10HoldersPercentage':'21.5','devHoldingPercentage':'1.2','volume1h':'5000','volume1hBuy':'3200','volume1hSell':'1800','buyTxCount1h':'44','sellTxCount1h':'20','uniqueBuyers1h':'31','uniqueSellers1h':'15','liquidity':'12000'}
    x=normalize(meta,dyn,{})
    assert x['holders']['count']==123 and x['holders']['top10Pct']==21.5
    assert x['trades']['windowSeconds']==3600 and x['trades']['uniqueBuyers']==31
    assert x['twitter']=='https://x.com/cat' and x['description']=='cat lore'

def test_binance_missing_fields_stay_missing():
    x=normalize({}, {'volume24h':'12.5'}, {})
    assert 'holders' not in x
    assert x['trades']['volume']==12.5 and x['trades']['windowSeconds']==86400
    assert 'uniqueBuyers' not in x['trades']
