"""Global TrenchNet launch filtration.

Every launchpad first writes to unified_launches. This worker is the only launch-alert
path: it applies the same duplicate-cluster and creator-velocity rules across all
launchpads before queuing Telegram delivery.
"""
import json, os, sqlite3, time
from launch_filter import assess
from scanner import deliver
from v2_intelligence import gate as v2_gate, render as v2_render, enabled as v2_enabled


def setup(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS global_filter_decisions(
      event_key TEXT PRIMARY KEY,
      decided_at INTEGER NOT NULL,
      allow INTEGER NOT NULL,
      reason TEXT NOT NULL,
      duplicate_count INTEGER NOT NULL DEFAULT 1,
      unique_creators INTEGER NOT NULL DEFAULT 1,
      creator_launches INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS global_outbox(
      id INTEGER PRIMARY KEY,
      recipient INTEGER NOT NULL,
      event_key TEXT NOT NULL,
      body TEXT NOT NULL,
      state TEXT NOT NULL DEFAULT 'queued',
      attempts INTEGER NOT NULL DEFAULT 0,
      next_try INTEGER NOT NULL DEFAULT 0,
      expires INTEGER NOT NULL DEFAULT 0,
      UNIQUE(recipient,event_key)
    );
    CREATE TABLE IF NOT EXISTS global_filter_health(
      id INTEGER PRIMARY KEY CHECK(id=1), checked INTEGER NOT NULL, message TEXT NOT NULL
    );
    ''')
    c.commit()



def holder_reward_policy(launchpad, metadata):
    """Fail closed for launchpads where TrenchNet promises tax-funded holder rewards.

    Other launchpads use the general launch filter and are not claimed to have this
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
    if decision.get('creator_launches',1)>1: lines.append(f'🔁 Creator launches (window): {decision["creator_launches"]}')
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


def process(c, recipient, now=None, limit=100, duplicate_window=None, creator_window=None, creator_limit=None):
    setup(c); now=int(time.time() if now is None else now)
    duplicate_window=int(os.environ.get('DUPLICATE_WINDOW_SECONDS','900') if duplicate_window is None else duplicate_window)
    creator_window=int(os.environ.get('CREATOR_WINDOW_SECONDS','1800') if creator_window is None else creator_window)
    creator_limit=int(os.environ.get('CREATOR_LAUNCH_LIMIT','3') if creator_limit is None else creator_limit)
    batch=int(os.environ.get('GLOBAL_FILTER_BATCH_SIZE','1000') if limit==100 else limit)
    pads=('flap','stonk','pons','embercurve','pumpfun')
    select_cols="event_key,chain,launchpad,address,creator,name,symbol,pair_symbol,source_height,bonding_progress,migrated,launched_at,metadata"
    total_intake=c.execute("SELECT COUNT(*) FROM unified_launches WHERE pipeline_state='intake'").fetchone()[0]
    if total_intake<=batch:
        # Preserve strict arrival order when the queue is small; duplicate/creator rules are order-sensitive.
        rows=c.execute(f"SELECT {select_cols} FROM unified_launches WHERE pipeline_state='intake' ORDER BY launched_at,id LIMIT ?",(batch,)).fetchall()
    else:
        # Under backlog pressure reserve capacity for every launchpad, then process the selected
        # rows in original arrival order. This prevents one noisy scanner starving the others.
        per_pad=max(20,batch//len(pads)); ids=[]
        for pad in pads:
            ids += [r[0] for r in c.execute("SELECT id FROM unified_launches WHERE pipeline_state='intake' AND launchpad=? ORDER BY launched_at DESC,id DESC LIMIT ?",(pad,per_pad)).fetchall()]
        ids=ids[:batch]
        if ids:
            marks=','.join('?' for _ in ids)
            rows=c.execute(f"SELECT {select_cols} FROM unified_launches WHERE id IN ({marks}) ORDER BY launched_at,id",ids).fetchall()
        else: rows=[]
    allowed=blocked=0
    for row in rows:
        event_key,chain,launchpad,address,creator,name,symbol,*_=row
        launched_at=int(row[-2] or 0); metadata=row[-1]; max_age=int(os.environ.get('MAX_LAUNCH_AGE_SECONDS','600'))
        bonding=row[9]; migrated=bool(row[10])
        v2_ok,v2_reason=v2_gate(c,event_key,bonding,migrated)
        if not v2_ok:
            decision={'allow':False,'reason':v2_reason,'duplicates':1,'unique_creators':1,'creator_launches':1}
        elif not holder_reward_policy(launchpad,metadata):
            decision={'allow':False,'reason':'holder_reward_policy','duplicates':1,'unique_creators':1,'creator_launches':1}
        elif launched_at and not v2_enabled() and (launched_at < now-max_age or launched_at > now+120):
            decision={'allow':False,'reason':'stale_launch','duplicates':1,'unique_creators':1,'creator_launches':1}
        elif v2_enabled():
            cross=c.execute("SELECT crossed_90_at FROM v2_intelligence WHERE event_key=?",(event_key,)).fetchone()
            cross_at=int(cross[0] or 0) if cross else 0
            if not cross_at or cross_at < now-max_age or cross_at > now+120:
                decision={'allow':False,'reason':'stale_90_crossing','duplicates':1,'unique_creators':1,'creator_launches':1}
            else:
                decision=assess(c,chain=chain,launchpad=launchpad,address=address,creator=creator,name=name,symbol=symbol,now=now,duplicate_window=duplicate_window,creator_window=creator_window,creator_limit=creator_limit)
        else:
            decision=assess(c,chain=chain,launchpad=launchpad,address=address,creator=creator,name=name,symbol=symbol,now=now,duplicate_window=duplicate_window,creator_window=creator_window,creator_limit=creator_limit)
        with c:
            c.execute('INSERT OR REPLACE INTO global_filter_decisions (event_key,decided_at,allow,reason,duplicate_count,unique_creators,creator_launches) VALUES(?,?,?,?,?,?,?)',(event_key,now,int(decision['allow']),decision['reason'],decision['duplicates'],decision['unique_creators'],decision['creator_launches']))
            if decision['allow']: allowed+=1
            else: blocked+=1
            if decision['reason'] in {'bonding_below_90','intelligence_incomplete'}:
                pipeline_state='v2_tracking' if decision['reason']=='bonding_below_90' else 'awaiting_intelligence'
            else:
                pipeline_state='approved' if decision['allow'] else 'filtered'
            c.execute("UPDATE unified_launches SET pipeline_state=? WHERE event_key=?",(pipeline_state,event_key))
    remaining=c.execute("SELECT COUNT(*) FROM unified_launches WHERE pipeline_state='intake'").fetchone()[0]
    # Include this cycle's decision reasons and launchpads in health. This makes a
    # zero-approved cycle diagnosable from /status instead of requiring Railway logs.
    keys=[r[0] for r in rows]
    reasons=[]; pads_seen=[]
    if keys:
        marks=','.join('?' for _ in keys)
        reasons=c.execute(f"SELECT reason,COUNT(*) FROM global_filter_decisions WHERE event_key IN ({marks}) GROUP BY reason ORDER BY COUNT(*) DESC",keys).fetchall()
        pads_seen=c.execute(f"SELECT launchpad,COUNT(*) FROM unified_launches WHERE event_key IN ({marks}) GROUP BY launchpad ORDER BY COUNT(*) DESC",keys).fetchall()
    reason_text=','.join(f'{k}={v}' for k,v in reasons) or 'none'
    pad_text=','.join(f'{k}={v}' for k,v in pads_seen) or 'none'
    with c: c.execute('INSERT OR REPLACE INTO global_filter_health VALUES(1,?,?)',(now,f'Global filter: {len(rows)} processed; {allowed} approved; {blocked} filtered; reasons[{reason_text}]; pads[{pad_text}]; intake_remaining={remaining}'))
    return {'processed':len(rows),'allowed':allowed,'blocked':blocked}

def run():
    if os.environ.get('GLOBAL_FILTER_ENABLED','true')!='true': return
    from bot import database,api
    recipient=int(os.environ.get('ADMIN_CHAT_ID','0') or 0)
    c=database();setup(c)
    print('TrenchNet global filter started.',flush=True)
    while True:
        try:
            process(c,recipient)
        except Exception as e:
            msg='Global filter error: '+type(e).__name__+': '+str(e)[:180]
            try:
                with c:c.execute('INSERT OR REPLACE INTO global_filter_health VALUES(1,?,?)',(int(time.time()),msg))
            except Exception: pass
            print(msg,flush=True)
        time.sleep(float(os.environ.get('GLOBAL_FILTER_POLL_SECONDS','3')))

if __name__=='__main__': run()
