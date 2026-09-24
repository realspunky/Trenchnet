"""V2-only qualification. V1 assess(), duplicate and creator filters are retired.
Raw launches are tracked by v2_tracker; only crossed and Stage2-ready events
reach intake. This worker applies the final launchpad-specific V2 policy.
"""
import json, os, time
from v2_intelligence import gate as v2_gate, enabled as v2_enabled
from alert_preferences import setup as pref_setup

def setup(c):
    c.executescript("""CREATE TABLE IF NOT EXISTS v2_qualification_decisions(
      event_key TEXT PRIMARY KEY,decided_at INTEGER NOT NULL,allow INTEGER NOT NULL,
      reason TEXT NOT NULL,duplicate_count INTEGER NOT NULL DEFAULT 1,
      unique_creators INTEGER NOT NULL DEFAULT 1,creator_launches INTEGER NOT NULL DEFAULT 1);
      CREATE TABLE IF NOT EXISTS v2_qualification_health(id INTEGER PRIMARY KEY CHECK(id=1),checked INTEGER NOT NULL,message TEXT NOT NULL);
    """)
    c.commit()

def holder_reward_policy(launchpad, metadata):
    """Fail closed for launchpads where TrenchNet promises tax-funded holder rewards.

    Other launchpads use their own V2 qualification and are not claimed to have this
    reward model.
    """
    try:
        meta=json.loads(metadata or '{}') if isinstance(metadata,str) else (metadata or {})
    except (TypeError,ValueError,json.JSONDecodeError):
        return False if launchpad in {'flap','stonk'} else True
    if launchpad=='flap':
        rate=meta.get('token_tax_bps')
        return meta.get('verified') is True and meta.get('holder_rewards') is True and rate in {100,200,300}
    if launchpad=='stonk':
        return meta.get('eligible') is True and meta.get('rate') in {100,200,300} and bool(meta.get('reward_mint'))
    return True

def explorer(chain,address):
    if chain=='bnb': return 'https://bscscan.com/token/'+address
    if chain=='solana': return 'https://solscan.io/token/'+address
    if chain=='robinhood': return 'https://explorer.mainnet.chain.robinhood.com/token/'+address
    return ''


def alert_body(row, decision, c=None):
    event_key,chain,launchpad,address,creator,name,symbol,pair_symbol,source_height,bonding,migrated,*links=row
    social_x_url=links[0] if len(links)>0 else ''
    website_url=links[1] if len(links)>1 else ''
    try: metadata=json.loads(links[2] or '{}') if len(links)>2 else {}
    except (TypeError,ValueError,json.JSONDecodeError): metadata={}
    pad={'flap':'Flap','stonk':'STOnK','pons':'PONS','embercurve':'EmberCurve','pumpfun':'Pump.fun'}.get(launchpad,launchpad)
    title=(name or 'Unknown token') + (f' ({symbol})' if symbol else '')
    lines=['📣 TRENCHNET — NEW LAUNCH',f'🪙 {title}',f'🌐 Network: {chain.title()}',f'🚀 Launchpad: {pad}',f'📋 Contract: {address}']
    if creator: lines.append(f'👤 Creator: {creator}')
    if pair_symbol: lines.append(f'💱 Pair: {pair_symbol}')
    if launchpad=='flap':
        rate=metadata.get('token_tax_bps')
        if rate in {100,200,300}: lines.append(f'💸 Token tax: {rate/100:g}%')
        if metadata.get('holder_rewards') is True:
            alloc=metadata.get('dividend_allocation_bps')
            lines.append('💰 Holder rewards: Enabled' + (f' ({alloc/100:g}% allocation)' if isinstance(alloc,(int,float)) else ''))
            if metadata.get('reward_token'): lines.append(f'🎁 Reward asset: {metadata["reward_token"]}')
    elif launchpad=='stonk':
        rate=metadata.get('rate')
        if rate in {100,200,300}: lines.append(f'💸 Transfer tax: {rate/100:g}%')
        if metadata.get('eligible') is True:
            reward=metadata.get('reward_symbol') or metadata.get('reward_mint') or 'Enabled'
            lines.append(f'💰 Holder rewards: {reward}')
    if bonding is not None: lines.append(f'📈 Bonding progress: {float(bonding):.2f}%')
    if migrated: lines.append('🎓 Status: Migrated / graduated')
    if source_height is not None: lines.append(f'🧱 Block/slot: {source_height}')
    link=explorer(chain,address)
    if link: lines.append('🔗 '+link)
    if social_x_url: lines.append('𝕏 X: '+social_x_url)
    if website_url: lines.append('🌐 Website: '+website_url)
    if c is not None: lines += v2_render(c,event_key)
    lines.append('ℹ️ Contract address is the unique token identity; names/tickers may repeat.')
    return '\n'.join(lines)


def process(c,now=None,limit=250):
    setup(c);now=int(time.time() if now is None else now)
    rows=c.execute("""SELECT event_key,launchpad,bonding_progress,migrated,metadata
      FROM unified_launches WHERE pipeline_state='intake' ORDER BY last_seen DESC LIMIT ?""",(limit,)).fetchall()
    approved=blocked=0
    for event_key,pad,progress,migrated,metadata in rows:
        ok,reason=v2_gate(c,event_key,progress,bool(migrated))
        if ok and not holder_reward_policy(pad,metadata):ok=False;reason='v2_holder_reward_policy'
        # Freshness is based on the verified crossing, not launch creation.
        cross=c.execute('SELECT crossed_90_at FROM v2_intelligence WHERE event_key=?',(event_key,)).fetchone()
        crossed=int(cross[0] or 0) if cross else 0
        max_age=int(os.environ.get('MAX_LAUNCH_AGE_SECONDS','600'))
        if ok and (not crossed or crossed < now-max_age or crossed > now+120):
            ok=False;reason='stale_bonding_crossing'
        with c:
            c.execute('INSERT OR REPLACE INTO v2_qualification_decisions VALUES(?,?,?,?,?,?,?)',
                      (event_key,now,int(ok),reason,1,1,1))
            state=('approved' if ok else ('v2_tracking' if reason=='bonding_below_60' else
                   'awaiting_intelligence' if reason=='intelligence_incomplete' else 'filtered'))
            c.execute('UPDATE unified_launches SET pipeline_state=? WHERE event_key=?',(state,event_key))
        approved+=int(ok);blocked+=int(not ok)
    with c:c.execute('INSERT OR REPLACE INTO v2_qualification_health VALUES(1,?,?)',
                     (now,f'V2 qualification: {len(rows)} processed; {approved} approved; {blocked} blocked'))
    return {'processed':len(rows),'approved':approved,'blocked':blocked}

def run():
    from bot import database
    c=database();setup(c)
    print('TrenchNet V2-only qualification started.',flush=True)
    while True:
        try:process(c)
        except Exception as e:print('V2 qualification error: '+str(e)[:180],flush=True)
        time.sleep(float(os.environ.get('V2_QUALIFICATION_POLL_SECONDS','3')))

if __name__=='__main__':run()
