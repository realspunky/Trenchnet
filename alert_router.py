"""Route globally-approved launches to users based on launchpad preferences."""
import os,time
from alert_preferences import setup as pref_setup, ensure_user, get
from global_filter import alert_body
from scanner import deliver

def setup(c):
    pref_setup(c)
    c.executescript('''
    CREATE TABLE IF NOT EXISTS alert_route_state(event_key TEXT PRIMARY KEY, routed_at INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS global_outbox(
      id INTEGER PRIMARY KEY, recipient INTEGER NOT NULL, event_key TEXT NOT NULL, body TEXT NOT NULL,
      state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
      next_attempt INTEGER NOT NULL DEFAULT 0, expires INTEGER NOT NULL DEFAULT 0,
      message_id INTEGER,
      UNIQUE(recipient,event_key));''')
    # Migrate older global_outbox databases created before the router used the
    # scanner delivery schema. Railway persistent volumes keep the old table,
    # so CREATE TABLE IF NOT EXISTS alone is not enough.
    cols={r[1] for r in c.execute('PRAGMA table_info(global_outbox)').fetchall()}
    if 'next_attempt' not in cols:
        c.execute('ALTER TABLE global_outbox ADD COLUMN next_attempt INTEGER NOT NULL DEFAULT 0')
    if 'message_id' not in cols:
        c.execute('ALTER TABLE global_outbox ADD COLUMN message_id INTEGER')
    # Old router rows were named queued; deliver() consumes pending rows.
    c.execute("UPDATE global_outbox SET state='pending' WHERE state='queued'")
    c.commit()

def recipients(c):
    admin=os.environ.get('ADMIN_CHAT_ID')
    if os.environ.get('PUBLIC_ALERTS_ENABLED')=='true':
        ids=[r[0] for r in c.execute('SELECT id FROM users').fetchall()]
        if admin: ids.append(int(admin))
        return sorted(set(ids))
    return [int(admin)] if admin else []

def process(c,now=None,limit=100):
    setup(c); now=int(time.time() if now is None else now)
    max_age=int(os.environ.get('MAX_LAUNCH_AGE_SECONDS','600'))
    with c:
        c.execute("""UPDATE global_outbox SET state='stale' WHERE state='pending' AND event_key IN
          (SELECT event_key FROM unified_launches WHERE launched_at>0 AND launched_at<?)""",(now-max_age,))
    rows=c.execute('''SELECT u.event_key,u.chain,u.launchpad,u.address,u.creator,u.name,u.symbol,u.pair_symbol,
      u.source_height,u.bonding_progress,u.migrated,u.social_x_url,u.website_url,d.duplicate_count,d.unique_creators,d.creator_launches,u.launched_at
      FROM unified_launches u JOIN global_filter_decisions d ON d.event_key=u.event_key
      LEFT JOIN alert_route_state r ON r.event_key=u.event_key
      WHERE d.allow=1 AND r.event_key IS NULL ORDER BY u.first_seen,u.id LIMIT ?''',(int(limit),)).fetchall()
    queued=0
    for x in rows:
        row=x[:13]; decision={'duplicates':x[13],'unique_creators':x[14],'creator_launches':x[15]}
        launched_at=int(x[16] or 0)
        max_age=int(os.environ.get('MAX_LAUNCH_AGE_SECONDS','600'))
        if launched_at and (launched_at < now-max_age or launched_at > now+120):
            with c:
                c.execute("UPDATE unified_launches SET pipeline_state='stale' WHERE event_key=?",(x[0],))
                c.execute('INSERT OR IGNORE INTO alert_route_state VALUES(?,?)',(x[0],now))
            continue
        event_key,_,pad,*_=row
        # STOnK alerts require resolved metadata. Leave the event unrouted so a
        # later metadata enrichment can make it eligible; never construct an
        # alert whose token name is missing/placeholder text.
        token_name=(row[5] or '').strip()
        token_symbol=(row[6] or '').strip()
        if pad=='stonk' and (not token_name or token_name.casefold() in {'unknown','unknown token'} or not token_symbol):
            continue
        body=alert_body(row,decision)
        with c:
            for uid in recipients(c):
                ensure_user(c,uid)
                if get(c,uid).get(pad,False):
                    c.execute("INSERT OR IGNORE INTO global_outbox(recipient,event_key,body,state,next_attempt,expires) VALUES(?,?,?,'pending',0,?)",(uid,event_key,body,now+600))
                    queued+=1
            c.execute('INSERT OR IGNORE INTO alert_route_state VALUES(?,?)',(event_key,now))
    return {'processed':len(rows),'queued':queued}

def enforce_preferences(c):
    """Cancel any still-pending global alert that no longer matches the user's current /alerts selection.

    This is a second gate at delivery time. It protects all five launchpads, including
    alerts that were queued before the user changed preferences.
    """
    setup(c)
    # First cancel any legacy STOnK alert that was queued before metadata was
    # resolved. This prevents an old "Unknown token" body from leaking out after upgrade.
    with c:
        c.execute("""UPDATE global_outbox SET state='metadata_blocked' WHERE state='pending' AND event_key IN
          (SELECT event_key FROM unified_launches WHERE launchpad='stonk' AND
           (name IS NULL OR TRIM(name)='' OR LOWER(TRIM(name)) IN ('unknown','unknown token') OR symbol IS NULL OR TRIM(symbol)=''))""")
    rows=c.execute("""SELECT o.id,o.recipient,u.launchpad
      FROM global_outbox o JOIN unified_launches u ON u.event_key=o.event_key
      WHERE o.state='pending'""").fetchall()
    cancelled=0
    for ident,uid,pad in rows:
        ensure_user(c,uid)
        if not get(c,uid).get(pad,False):
            with c:c.execute("UPDATE global_outbox SET state='preference_blocked' WHERE id=? AND state='pending'",(ident,))
            cancelled+=1
    return cancelled

def deliver_selected(c,token,send):
    # Re-check preferences immediately before each Telegram send. This makes the
    # preference system authoritative for Flap, STOnK, PONS, EmberCurve and Pump.fun.
    enforce_preferences(c)
    return deliver(c,token,send,table='global_outbox')

def drain(c,token,send,limit=100):
    # Enforce once per batch, then drain immediately. No fixed sleep between pads.
    enforce_preferences(c)
    handled=0
    for _ in range(int(limit)):
        if not deliver(c,token,send,table='global_outbox'): break
        handled+=1
    return handled

def run():
    from bot import database,api
    c=database(); setup(c); token=os.environ['TELEGRAM_BOT_TOKEN']
    print('TrenchNet alert router started.',flush=True)
    while True:
        try:
            process(c)
            drain(c,token,api)
        except Exception as e: print('Alert router error: '+type(e).__name__+': '+str(e),flush=True)
        time.sleep(float(os.environ.get('ALERT_ROUTER_POLL_SECONDS','3')))
if __name__=='__main__':run()
