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
      state TEXT NOT NULL DEFAULT 'queued', attempts INTEGER NOT NULL DEFAULT 0,
      next_try INTEGER NOT NULL DEFAULT 0, expires INTEGER NOT NULL DEFAULT 0,
      UNIQUE(recipient,event_key));''')
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
    rows=c.execute('''SELECT u.event_key,u.chain,u.launchpad,u.address,u.creator,u.name,u.symbol,u.pair_symbol,
      u.source_height,u.bonding_progress,u.migrated,u.social_x_url,u.website_url,d.duplicate_count,d.unique_creators,d.creator_launches
      FROM unified_launches u JOIN global_filter_decisions d ON d.event_key=u.event_key
      LEFT JOIN alert_route_state r ON r.event_key=u.event_key
      WHERE d.allow=1 AND r.event_key IS NULL ORDER BY u.launched_at,u.id LIMIT ?''',(int(limit),)).fetchall()
    queued=0
    for x in rows:
        row=x[:13]; decision={'duplicates':x[13],'unique_creators':x[14],'creator_launches':x[15]}
        event_key,_,pad,*_=row
        body=alert_body(row,decision)
        with c:
            for uid in recipients(c):
                ensure_user(c,uid)
                if get(c,uid).get(pad,False):
                    c.execute('INSERT OR IGNORE INTO global_outbox(recipient,event_key,body,expires) VALUES(?,?,?,?)',(uid,event_key,body,now+600))
                    queued+=1
            c.execute('INSERT OR IGNORE INTO alert_route_state VALUES(?,?)',(event_key,now))
    return {'processed':len(rows),'queued':queued}

def run():
    from bot import database,api
    c=database(); setup(c); token=os.environ['TELEGRAM_BOT_TOKEN']
    print('TrenchNet alert router started.',flush=True)
    while True:
        try:
            process(c)
            for _ in range(20): deliver(c,token,api,table='global_outbox'); time.sleep(.25)
        except Exception as e: print('Alert router error: '+type(e).__name__+': '+str(e),flush=True)
        time.sleep(float(os.environ.get('ALERT_ROUTER_POLL_SECONDS','3')))
if __name__=='__main__':run()
