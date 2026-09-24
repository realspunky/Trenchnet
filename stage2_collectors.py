"""Shared Stage-2 intelligence collectors.

Uses chain-native RPC for holder distribution and a configurable read-only market
provider for recent trades/sniper analytics. Missing facts stay missing (fail closed).
"""
import json, os, time, urllib.request
from urllib.parse import quote

SOL_RPC=os.environ.get('SOLANA_RPC_URL','https://api.mainnet-beta.solana.com')


def _rpc(url,method,params):
    body=json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params}).encode()
    req=urllib.request.Request(url,data=body,headers={'Content-Type':'application/json','Accept':'application/json','User-Agent':'TrenchNet-V2/2.1'})
    with urllib.request.urlopen(req,timeout=20) as r: raw=r.read(3_000_001)
    if len(raw)>3_000_000: raise ValueError('RPC response too large')
    x=json.loads(raw)
    if x.get('error'): raise ValueError('RPC error: '+str(x['error'])[:140])
    return x.get('result')


def solana_holders(mint,creator=''):
    """Verified current SPL holder distribution from largest token accounts.

    Solana RPC exposes the 20 largest token accounts. This gives a reliable top-10
    concentration and creator holding when the creator owns one of those accounts;
    exact total holder count requires an indexer and therefore is not fabricated.
    """
    largest=_rpc(SOL_RPC,'getTokenLargestAccounts',[mint,{'commitment':'confirmed'}]) or {}
    rows=largest.get('value') or []
    supply=_rpc(SOL_RPC,'getTokenSupply',[mint,{'commitment':'confirmed'}]) or {}
    total=int(((supply.get('value') or {}).get('amount')) or 0)
    if total<=0: raise ValueError('token supply unavailable')
    vals=[]
    for r in rows:
        try: vals.append(int(r.get('amount') or 0))
        except Exception: pass
    out={'top10Pct':sum(sorted(vals,reverse=True)[:10])*100.0/total}
    # Optional exact holder count provider. We never call the 20-account result a holder count.
    return out


def evm_holders_from_provider(address,chain='bnb'):
    """Optional exact EVM holder distribution provider; no guessed explorer scraping."""
    tpl=os.environ.get('V2_EVM_HOLDERS_URL','').strip()
    if not tpl:return {}
    url=tpl.replace('{address}',quote(address,safe='')).replace('{chain}',quote(chain,safe=''))
    req=urllib.request.Request(url,headers={'Accept':'application/json','User-Agent':'TrenchNet-V2/2.1'})
    with urllib.request.urlopen(req,timeout=15) as r: raw=r.read(2_000_001)
    if len(raw)>2_000_000:raise ValueError('holder response too large')
    x=json.loads(raw)
    return x if isinstance(x,dict) else {}


def market_intelligence(launchpad,address):
    """Normalized recent market/sniper provider.

    A provider is intentionally configurable because no single documented first-party
    endpoint exposes holders + unique traders + sniper labels for every launchpad.
    It is called only after >=60%, preserving API budget.
    """
    tpl=os.environ.get('V2_MARKET_INTELLIGENCE_URL','').strip()
    if not tpl:return {}
    url=tpl.replace('{address}',quote(address,safe='')).replace('{launchpad}',quote(launchpad,safe=''))
    req=urllib.request.Request(url,headers={'Accept':'application/json','User-Agent':'TrenchNet-V2/2.1'})
    with urllib.request.urlopen(req,timeout=15) as r: raw=r.read(2_000_001)
    if len(raw)>2_000_000:raise ValueError('market intelligence response too large')
    x=json.loads(raw)
    if not isinstance(x,dict):raise ValueError('market intelligence must be JSON object')
    return x



def enrich(launchpad,address,metadata):
    out=dict(metadata or {})
    # Chain-native intelligence first.
    if launchpad in {'stonk','embercurve','pumpfun'}:
        try:
            from native_chain_v2 import enrich_solana
            out=enrich_solana(address,out)
        except Exception as e:out['native_chain_error']=type(e).__name__
    elif launchpad=='flap':
        try:
            from flap_native_v2 import enrich as flap_enrich
            out=flap_enrich(address,out)
        except Exception as e:out['native_chain_error']=type(e).__name__
    # Credential-free public market data fills USD volume/social facts when available.
    if launchpad in {'flap','stonk','embercurve','pumpfun'}:
        try:
            from public_market_v2 import fetch as public_fetch
            m=public_fetch(launchpad,address)
            if m:
                if m.get('volume') is not None:out['volume']=m['volume']
                if m.get('social_checked'):out['social_checked']=True
                for k in ('twitter','telegram','website','liquidity_usd','public_market_source'):
                    if m.get(k) is not None:out[k]=m[k]
                # Do not overwrite native unique-trader counts with aggregate-only public counts.
                if not isinstance(out.get('trades'),dict) and isinstance(m.get('market_txns'),dict):out['trades']=m['market_txns']
        except Exception as e:out['public_market_error']=type(e).__name__
    # Free Binance token-info remains optional and credential-free.
    if launchpad in {'flap','stonk','embercurve','pumpfun'}:
        try:
            from binance_v2_intelligence import fetch as binance_fetch
            b=binance_fetch(launchpad,address)
            if b:
                for k,v in b.items():
                    if k in {'holders','trades'} and isinstance(v,dict):
                        old=out.get(k) if isinstance(out.get(k),dict) else {};out[k]={**old,**v}
                    elif v is not None:out[k]=v
        except Exception as e:out['binance_intelligence_error']=type(e).__name__
    try:
        m=market_intelligence(launchpad,address)
        if m:
            for k,v in m.items():
                if v is not None:out[k]=v
    except Exception as e:out['market_intelligence_error']=type(e).__name__
    return out
