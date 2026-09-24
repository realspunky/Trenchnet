import native_chain_v2 as n

def test_holder_intelligence_exact_owner_aggregation(monkeypatch):
    monkeypatch.setattr(n,'_token_accounts',lambda m:[('a',50),('a',10),('b',30),('dev',10)])
    monkeypatch.setattr(n,'_rpc',lambda method,params,timeout=25:{'value':{'amount':'100'}} if method=='getTokenSupply' else None)
    h,owners,total=n.solana_holder_intelligence('mint','dev')
    assert h['count']==3 and h['top10Pct']==100 and h['devPct']==10 and owners['a']==60 and total==100

def test_wallet_delta_prefers_signer():
    tx={'transaction':{'message':{'accountKeys':[{'pubkey':'w','signer':True},{'pubkey':'ta','signer':False}]}},'meta':{
      'preTokenBalances':[{'accountIndex':0,'mint':'m','owner':'w','uiTokenAmount':{'amount':'1'}}],
      'postTokenBalances':[{'accountIndex':0,'mint':'m','owner':'w','uiTokenAmount':{'amount':'9'}}]}}
    assert n._wallet_token_delta(tx,'m')==('w',8)

def test_no_fake_volume(monkeypatch):
    monkeypatch.setattr(n,'_rpc',lambda method,params,timeout=25: [] if method=='getSignaturesForAddress' else None)
    x=n.solana_trade_intelligence('m',None,3600)
    assert x['trades']['buys']==0 and 'volume' not in x['trades']
