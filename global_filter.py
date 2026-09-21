"""Global TrenchNet launch filtration.

Every launchpad first writes to unified_launches. This worker is the only launch-alert
path: it applies the same duplicate-cluster and creator-velocity rules across all
launchpads before queuing Telegram delivery.
"""
import os, sqlite3, time
from launch_filter import assess
from scanner import deliver


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


def explorer(chain,address):
    if chain=='bnb': return 'https://bscscan.com/token/'+address
    if chain=='solana': return 'https://solscan.io/token/'+address
    if chain=='robinhood': return 'https://explorer.mainnet.chain.robinhood.com/token/'+address
    return ''


def alert_body(row, decision):
    event_key,chain,launchpad,address,creator,name,symbol,pair_symbol,source_height,bonding,migrated,*links=row
    social_x_url=links[0] if len(links)>0 else ''
    website_url=links[1] if len(links)>1 else ''
    pad={'flap':'Flap','stonk':'STOnK','pons':'PONS','embercurve':'EmberCurve','pumpfun':'Pump.fun'}.get(launchpad,launchpad)
    title=(name or 'Unknown token') + (f' ({symbol})' if symbol else '')
    lines=['📣 TRENCHNET — NEW LAUNCH',f'🪙 {title}',f'🌐 Network: {chain.title()}',f'🚀 Launchpad: {pad}',f'📋 Contract: {address}']
    if creator: lines.append(f'👤 Creator: {creator}')
    if pair_symbol: lines.append(f'💱 Pair: {pair_symbol}')
    if decision.get('creator_launches',1)>1: lines.append(f'🔁 Creator launches (window): {decision["creator_launches"]}')
    if bonding is not None: lines.append(f'📈 Bonding progress: {float(bonding):.2f}%')
    if migrated: lines.append('🎓 Status: Migrated / graduated')
    if source_height is not None: lines.append(f'🧱 Block/slot: {source_height}')
    link=explorer(chain,address)
    if link: lines.append('🔗 '+link)
    if social_x_url: lines.append('𝕏 X: '+social_x_url)
    if website_url: lines.append('🌐 Website: '+website_url)
    lines.append('ℹ️ Contract address is the unique token identity; names/tickers may repeat.')
    return '\n'.join(lines)


def process(c, recipient, now=None, limit=100, duplicate_window=None, creator_window=None, creator_limit=None):
    setup(c); now=int(time.time() if now is None else now)
    duplicate_window=int(os.environ.get('DUPLICATE_WINDOW_SECONDS','900') if duplicate_window is None else duplicate_window)
    creator_window=int(os.environ.get('CREATOR_WINDOW_SECONDS','1800') if creator_window is None else creator_window)
    creator_limit=int(os.environ.get('CREATOR_LAUNCH_LIMIT','3') if creator_limit is None else creator_limit)
    rows=c.execute('''SELECT event_key,chain,launchpad,address,creator,name,symbol,pair_symbol,source_height,
      bonding_progress,migrated FROM unified_launches WHERE pipeline_state='intake'
      ORDER BY launched_at,id LIMIT ?''',(int(limit),)).fetchall()
    allowed=blocked=0
    for row in rows:
        event_key,chain,launchpad,address,creator,name,symbol,*_=row
        decision=assess(c,chain=chain,launchpad=launchpad,address=address,creator=creator,name=name,symbol=symbol,
            now=now,duplicate_window=duplicate_window,creator_window=creator_window,creator_limit=creator_limit)
        with c:
            c.execute('''INSERT OR REPLACE INTO global_filter_decisions
              (event_key,decided_at,allow,reason,duplicate_count,unique_creators,creator_launches)
              VALUES(?,?,?,?,?,?,?)''',(event_key,now,int(decision['allow']),decision['reason'],decision['duplicates'],decision['unique_creators'],decision['creator_launches']))
            if decision['allow']:
                allowed+=1
            else: blocked+=1
            c.execute("UPDATE unified_launches SET pipeline_state=? WHERE event_key=?",
                      ('approved' if decision['allow'] else 'filtered',event_key))
    with c:c.execute('INSERT OR REPLACE INTO global_filter_health VALUES(1,?,?)',
        (now,f'Global filter: {len(rows)} processed; {allowed} approved; {blocked} filtered'))
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
            print('Global filter error: '+type(e).__name__+': '+str(e),flush=True)
        time.sleep(float(os.environ.get('GLOBAL_FILTER_POLL_SECONDS','3')))

if __name__=='__main__': run()
