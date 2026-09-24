import os
import binance_web3_v2 as b

def test_not_configured_is_fail_closed(monkeypatch):
    monkeypatch.delenv('BINANCE_WEB3_API_KEY',raising=False); monkeypatch.delenv('BINANCE_WEB3_SECRET_KEY',raising=False)
    assert b.fetch('pumpfun','mint') == {}

def test_advanced_normalization(monkeypatch):
    monkeypatch.setenv('BINANCE_WEB3_API_KEY','k'); monkeypatch.setenv('BINANCE_WEB3_SECRET_KEY','s')
    def fake(path,params=None,method='GET',body=None):
        tag=(params or {}).get('tagFilter')
        if path.endswith('/token/holder'):
            if tag==5:return [{'holdingPercent':'2','holdAmount':'10','soldAmount':'0'},{'holdingPercent':'1','holdAmount':'0','soldAmount':'4'}]
            if tag==6:return [{'holdingPercent':'1'}]
            return [{'holdingPercent':'4'},{'holdingPercent':'3'}]
        if path.endswith('tokenDevInfo'):
            return {'devLaunchedInfo':{'totalToken':'5','migratedCount':'2'},'devHoldingInfo':{'devHoldingPercent':'1.5','devAddress':'dev','fundingSource':'fund'}}
        raise AssertionError(path)
    monkeypatch.setattr(b,'_request',fake)
    monkeypatch.setattr(b,'_trade_window',lambda *a,**k:{'buys':4,'sells':2,'uniqueBuyers':3,'uniqueSellers':2,'buyVolume':10.0,'sellVolume':4.0,'volume':14.0,'windowSeconds':3600})
    x=b.fetch('pumpfun','mint')
    assert x['holders']['top10Pct']==7
    assert x['holders']['devPct']==1.5
    assert x['snipers']['count']==2 and x['snipers']['concentrationPct']==3
    assert x['snipers']['largestPct']==2
    assert x['bundled_wallet_count']==1
    assert x['developer']['totalLaunched']==5
    assert x['trades']['uniqueBuyers']==3
