"""Compact admin-only V2 diagnostic status.

This deliberately does not mix V1 access/trial/pilot history into V2 testing.
Counts are active-window diagnostics so persistent /data history does not swamp
what the current V2 worker is doing.
"""
import os, sqlite3, time
from v2_intelligence import REQUIRED, setup as v2_setup

ACTIVE_SECONDS = int(os.environ.get('V2_STATUS_ACTIVE_SECONDS','600'))
PADS = (('flap','Flap'),('stonk','STOnK'),('pons','PONS'),('embercurve','EmberCurve'),('pumpfun','Pump.fun'))

def _one(c, sql, args=(), default=0):
    try:
        r=c.execute(sql,args).fetchone()
        return default if not r or r[0] is None else r[0]
    except sqlite3.OperationalError:
        return default

def _health(c, table, stale=180):
    try:r=c.execute(f'SELECT updated,status FROM {table} WHERE id=1').fetchone()
    except sqlite3.OperationalError:return '⚪ no report'
    if not r:return '⚪ no report'
    age=max(0,int(time.time())-int(r[0]))
    return ('🟢' if age <= stale else '🟡')+f' {age}s ago'

def _missing(c, cutoff):
    # Only inspect active tokens that actually crossed the mandatory gate.
    try:
        rows=c.execute("""SELECT description,social_checked,holder_count,top10_holder_pct,
          sniper_count,sniper_concentration_pct,buy_count,sell_count,unique_buyers,unique_sellers,volume
          FROM v2_intelligence WHERE crossed_90_at IS NOT NULL AND state='awaiting_intelligence' AND updated_at>=?""",(cutoff,)).fetchall()
    except sqlite3.OperationalError:return {}
    names=list(REQUIRED); out={k:0 for k in names}
    for r in rows:
        d=dict(zip(names,r))
        for k in names:
            bad=(not str(d[k] or '').strip()) if k=='description' else (d[k]!=1 if k=='social_checked' else d[k] is None)
            if bad:out[k]+=1
    return {k:v for k,v in out.items() if v}

def build(c):
    now=int(time.time()); cutoff=now-ACTIVE_SECONDS
    v2_setup(c)
    try:h=c.execute('SELECT updated,message FROM v2_health WHERE id=1').fetchone()
    except sqlite3.OperationalError:h=None
    if h:
        age=max(0,now-int(h[0])); engine=('🟢 Running' if age<=30 else '🟡 Stale')+f' · {age}s ago'
    else:engine='🔴 No tracker report'
    public='🟢 ON' if os.environ.get('PUBLIC_ALERTS_ENABLED','false').lower()=='true' else '🔴 OFF'
    lines=['TRENCHNET V2 — PRIVATE TEST', '', f'Engine: {engine}', f'Public delivery: {public}', 'Bonding gate: ≥90% mandatory', f'Active window: last {ACTIVE_SECONDS//60}m', '']

    total_tracking=total_wait=total_ready=0
    health_tables={'flap':'scanner_health','stonk':'stonk_health','pons':'pons_health','embercurve':'ember_health','pumpfun':'pumpfun_health'}
    for pad,label in PADS:
        tracking=_one(c,"SELECT COUNT(*) FROM v2_intelligence WHERE launchpad=? AND state='tracking' AND updated_at>=?",(pad,cutoff))
        waiting=_one(c,"SELECT COUNT(*) FROM v2_intelligence WHERE launchpad=? AND state='awaiting_intelligence' AND crossed_90_at IS NOT NULL AND updated_at>=?",(pad,cutoff))
        ready=_one(c,"SELECT COUNT(*) FROM v2_intelligence WHERE launchpad=? AND state='ready' AND updated_at>=?",(pad,cutoff))
        crossed=_one(c,"SELECT COUNT(*) FROM v2_intelligence WHERE launchpad=? AND crossed_90_at>=?",(pad,cutoff))
        errors=_one(c,"SELECT COUNT(*) FROM v2_intelligence WHERE launchpad=? AND updated_at>=? AND last_error<>''",(pad,cutoff))
        total_tracking+=tracking;total_wait+=waiting;total_ready+=ready
        lines += [f'{label.upper()}  {_health(c,health_tables[pad],300 if pad=="stonk" else 180)}',
                  f'Tracking <90%: {tracking} · Crossed 90%: {crossed}',
                  f'Awaiting intel: {waiting} · Ready: {ready} · Errors: {errors}', '']

    missing=_missing(c,cutoff)
    lines += ['STAGE 2',f'Below 90% / tracking: {total_tracking}',f'Awaiting intelligence: {total_wait}',f'Ready: {total_ready}']
    if missing:
        pretty={'description':'description','social_checked':'social check','holder_count':'holders','top10_holder_pct':'top 10','sniper_count':'sniper count','sniper_concentration_pct':'sniper concentration','buy_count':'buys','sell_count':'sells','unique_buyers':'unique buyers','unique_sellers':'unique sellers','volume':'volume'}
        lines.append('Missing: '+', '.join(f'{pretty[k]}={v}' for k,v in missing.items()))
    else:lines.append('Missing: none in active awaiting set')

    try:
        states=c.execute("""SELECT o.state,COUNT(*) FROM global_outbox o
          JOIN v2_intelligence v ON v.event_key=o.event_key
          WHERE v.updated_at>=? AND o.state IN ('pending','sent','v2_blocked','preference_blocked','stale','metadata_blocked')
          GROUP BY o.state""",(cutoff,)).fetchall()
    except sqlite3.OperationalError:states=[]
    sm=dict(states)
    lines += ['', 'DELIVERY SAFETY', f"Queued: {sm.get('pending',0)} · Sent: {sm.get('sent',0)}", f"V2 blocked: {sm.get('v2_blocked',0)} · Preference blocked: {sm.get('preference_blocked',0)}", f"Stale/replay: {sm.get('stale',0)} · Metadata blocked: {sm.get('metadata_blocked',0)}"]
    return '\n'.join(lines)
