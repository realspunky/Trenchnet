"""Credential-free Stage-2 collectors.

Solana intelligence is derived from standard RPC only. Sniper/bundle fields are
explicit deterministic heuristics, never third-party labels:
- sniper = wallet whose first observed net buy occurred within N seconds of launch
- bundle = >=2 early buyers whose first buys landed in the same slot
The collector only publishes those fields when transaction history coverage reaches
the launch window; otherwise they remain missing and V2 fails closed.
"""
import json, os, time, urllib.request

SOL_RPC=os.environ.get('SOLANA_RPC_URL','https://api.mainnet-beta.solana.com')
TOKEN_PROGRAMS=(
 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA',
 'TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb',
)

def _rpc(method,params,timeout=25):
    body=json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params}).encode()
    req=urllib.request.Request(SOL_RPC,data=body,headers={'Content-Type':'application/json','Accept':'application/json','User-Agent':'TrenchNet-V2-native/2.4'})
    with urllib.request.urlopen(req,timeout=timeout) as r: raw=r.read(12_000_001)
    if len(raw)>12_000_000: raise ValueError('Solana RPC response too large')
    x=json.loads(raw)
    if x.get('error'): raise ValueError('Solana RPC error: '+str(x['error'])[:180])
    return x.get('result')

def _token_accounts(mint):
    rows=[]
    for program in TOKEN_PROGRAMS:
        try:
            got=_rpc('getProgramAccounts',[program,{'encoding':'jsonParsed','commitment':'confirmed','filters':[{'memcmp':{'offset':0,'bytes':mint}}]}]) or []
        except Exception:
            continue
        for r in got:
            try:
                info=r['account']['data']['parsed']['info']; amt=int(info['tokenAmount']['amount']); owner=str(info['owner'])
                if amt>0: rows.append((owner,amt))
            except Exception: pass
    if not rows: raise ValueError('SPL holder accounts unavailable')
    return rows

def solana_holder_intelligence(mint,creator=''):
    rows=_token_accounts(mint)
    by_owner={}
    for owner,amt in rows: by_owner[owner]=by_owner.get(owner,0)+amt
    supply=_rpc('getTokenSupply',[mint,{'commitment':'confirmed'}]) or {}
    total=int(((supply.get('value') or {}).get('amount')) or 0)
    if total<=0: raise ValueError('SPL supply unavailable')
    vals=sorted(by_owner.values(),reverse=True)
    out={'count':len(by_owner),'top10Pct':sum(vals[:10])*100.0/total}
    if creator: out['devPct']=by_owner.get(str(creator),0)*100.0/total
    return out,by_owner,total

def _keys(tx):
    msg=((tx or {}).get('transaction') or {}).get('message') or {}
    raw=msg.get('accountKeys') or []
    out=[]
    for k in raw:
        if isinstance(k,str):out.append((k,False))
        elif isinstance(k,dict):out.append((str(k.get('pubkey') or ''),bool(k.get('signer'))))
    return out

def _wallet_token_delta(tx,mint):
    meta=(tx or {}).get('meta') or {}; keys=_keys(tx)
    owners={}; pre={}; post={}
    for side,dst in ((meta.get('preTokenBalances') or [],pre),(meta.get('postTokenBalances') or [],post)):
        for b in side:
            if str(b.get('mint'))!=mint: continue
            owner=str(b.get('owner') or '')
            if not owner:
                idx=b.get('accountIndex')
                if isinstance(idx,int) and idx<len(keys):owner=keys[idx][0]
            if not owner:continue
            try:amt=int(((b.get('uiTokenAmount') or {}).get('amount')) or 0)
            except Exception:continue
            dst[owner]=dst.get(owner,0)+amt
    deltas={o:post.get(o,0)-pre.get(o,0) for o in set(pre)|set(post)}
    signers=[k for k,s in keys if s]
    # Prefer a signer with a token delta; otherwise largest nonzero owner delta.
    for s in signers:
        if deltas.get(s):return s,deltas[s]
    nz=[(o,d) for o,d in deltas.items() if d]
    if not nz:return '',0
    return max(nz,key=lambda x:abs(x[1]))

def solana_trade_intelligence(mint,launched_at=None,window_seconds=3600):
    now=int(time.time()); cutoff=now-int(window_seconds); launch=int(launched_at or 0)
    before=None; sigs=[]; reached_launch=(not launch); max_pages=max(1,min(12,int(os.environ.get('V2_NATIVE_SOL_TX_PAGES','6'))))
    for _ in range(max_pages):
        cfg={'limit':1000,'commitment':'confirmed'}
        if before:cfg['before']=before
        batch=_rpc('getSignaturesForAddress',[mint,cfg]) or []
        if not batch:break
        sigs.extend(batch); before=batch[-1].get('signature')
        oldest=min([int(x.get('blockTime') or now) for x in batch] or [now])
        if launch and oldest<=launch: reached_launch=True;break
        if not launch and oldest<=cutoff:break
    recent=[]; early=[]
    sniper_window=max(15,int(os.environ.get('V2_NATIVE_SNIPER_WINDOW_SECONDS','120')))
    for s in sigs:
        bt=int(s.get('blockTime') or 0)
        need_recent=bt>=cutoff
        need_early=bool(launch and launch<=bt<=launch+sniper_window)
        if not (need_recent or need_early) or s.get('err') is not None:continue
        tx=_rpc('getTransaction',[s['signature'],{'encoding':'jsonParsed','commitment':'confirmed','maxSupportedTransactionVersion':1}])
        if not tx or (tx.get('meta') or {}).get('err') is not None:continue
        wallet,delta=_wallet_token_delta(tx,mint)
        if not wallet or not delta:continue
        row=(wallet,delta,bt,int(tx.get('slot') or s.get('slot') or 0))
        if need_recent:recent.append(row)
        if need_early and delta>0:early.append(row)
    buys=[r for r in recent if r[1]>0]; sells=[r for r in recent if r[1]<0]
    out={'trades':{'buys':len(buys),'sells':len(sells),'uniqueBuyers':len({r[0] for r in buys}),'uniqueSellers':len({r[0] for r in sells}),'windowSeconds':int(window_seconds)}}
    # Native RPC has no USD oracle here, so volume remains absent rather than fabricated.
    if launch and reached_launch:
        first={}
        for w,d,bt,slot in sorted(early,key=lambda r:(r[2],r[3])): first.setdefault(w,(d,bt,slot))
        holders,total_map,total_supply=solana_holder_intelligence(mint)
        sniper_wallets=set(first)
        held=sum(total_map.get(w,0) for w in sniper_wallets)
        pcts=[total_map.get(w,0)*100.0/total_supply for w in sniper_wallets]
        slots={}
        for w,(d,bt,slot) in first.items():slots.setdefault(slot,[]).append(w)
        bundled={w for ws in slots.values() if len(ws)>=2 for w in ws}
        out['snipers']={'count':len(sniper_wallets),'concentrationPct':held*100.0/total_supply,'largestPct':max(pcts) if pcts else 0.0,'stillHolding':sum(1 for w in sniper_wallets if total_map.get(w,0)>0),'sold':sum(1 for w in sniper_wallets if total_map.get(w,0)==0),'method':'native_first_buy_window'}
        out['bundled_wallet_count']=len(bundled);out['bundle_method']='same_slot_early_buyers'
        out['native_history_complete']=True
    return out

def enrich_solana(mint,metadata):
    out=dict(metadata or {}); creator=out.get('creator') or out.get('deployer') or ''
    holders,_owners,_supply=solana_holder_intelligence(mint,creator)
    old=out.get('holders') if isinstance(out.get('holders'),dict) else {};out['holders']={**old,**holders}
    launched=out.get('launched_at') or out.get('createdAt') or out.get('created_at')
    trade=solana_trade_intelligence(mint,launched,int(os.environ.get('V2_TRADE_WINDOW_SECONDS','3600')))
    for k,v in trade.items():out[k]=v
    out['native_chain_intelligence']=True
    return out
