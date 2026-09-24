"""Credential-free public market enrichment.

DEX Screener is used only for market/social facts it explicitly returns. It is never
used for the mandatory launchpad bonding gate or sniper classification.
"""
import json, urllib.request, urllib.parse

CHAIN={'flap':'bsc','stonk':'solana','embercurve':'solana','pumpfun':'solana'}

def _get(url):
    req=urllib.request.Request(url,headers={'Accept':'application/json','User-Agent':'TrenchNet-V2/2.6'})
    with urllib.request.urlopen(req,timeout=12) as r: raw=r.read(3_000_001)
    if len(raw)>3_000_000: raise ValueError('public market response too large')
    return json.loads(raw)

def fetch(launchpad,address):
    chain=CHAIN.get(launchpad)
    if not chain:return {}
    url='https://api.dexscreener.com/token-pairs/v1/'+chain+'/'+urllib.parse.quote(address,safe='')
    rows=_get(url)
    if not isinstance(rows,list) or not rows:return {}
    # Prefer the deepest pool; bonding-curve-only tokens may have no pair and then fail closed.
    def liq(x):
        try:return float(((x.get('liquidity') or {}).get('usd')) or 0)
        except Exception:return 0.0
    p=max((x for x in rows if isinstance(x,dict)),key=liq,default=None)
    if not p:return {}
    tx=(p.get('txns') or {}).get('h1') or {}; vol=(p.get('volume') or {}).get('h1')
    out={'public_market_source':'dexscreener','liquidity_usd':liq(p)}
    if vol is not None:
        try:out['volume']=float(vol)
        except Exception:pass
    if isinstance(tx,dict):
        out['market_txns']={'buys':tx.get('buys'),'sells':tx.get('sells'),'windowSeconds':3600}
    info=p.get('info') or {}; socials=info.get('socials') or []; websites=info.get('websites') or []
    out['social_checked']=True
    for s in socials:
        if not isinstance(s,dict):continue
        platform=str(s.get('type') or s.get('platform') or '').lower(); url=s.get('url')
        if platform in {'twitter','x'} and url:out['twitter']=url
        elif platform=='telegram' and url:out['telegram']=url
    if websites and isinstance(websites[0],dict) and websites[0].get('url'):out['website']=websites[0]['url']
    return out
