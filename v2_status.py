"""Admin-only V2 diagnostic status, isolated from persistent V1/history counters."""
import os, sqlite3, time
from v2_intelligence import REQUIRED, setup as v2_setup, session_started_at

ACTIVE_SECONDS = int(os.environ.get('V2_STATUS_ACTIVE_SECONDS','600'))
PADS = (('flap','Flap'),('stonk','STOnK'),('pons','PONS'),('embercurve','EmberCurve'),('pumpfun','Pump.fun'))

def _one(c, sql, args=(), default=0):
    try:
        r=c.execute(sql,args).fetchone(); return default if not r or r[0] is None else r[0]
    except sqlite3.OperationalError:return default

def _health(c, table, green=60, yellow=180):
    try:r=c.execute(f'SELECT updated,status FROM {table} WHERE id=1').fetchone()
    except sqlite3.OperationalError:return '⚪ no report'
    if not r:return '⚪ no report'
    age=max(0,int(time.time())-int(r[0]))
    icon='🟢' if age<=green else ('🟡' if age<=yellow else '🔴')
    suffix=''
    status=str(r[1] or '').strip()
    if icon!='🟢' and status and status.lower() not in {'ok','running'}:
        suffix=' · '+status[:90]
    return f'{icon} {age}s ago{suffix}'

def _missing(c, cutoff):
    # Eligibility is based on when the mandatory gate was crossed, never updated_at.
    try:
        rows=c.execute("""SELECT description,social_checked,holder_count,top10_holder_pct,
          sniper_count,sniper_concentration_pct,buy_count,sell_count,unique_buyers,unique_sellers,volume
          FROM v2_intelligence WHERE state='awaiting_intelligence' AND crossed_90_at>=?""",(cutoff,)).fetchall()
    except sqlite3.OperationalError:return {}
    names=list(REQUIRED); out={k:0 for k in names}
    for r in rows:
        d=dict(zip(names,r))
        for k in names:
            bad=(not str(d[k] or '').strip()) if k=='description' else (d[k]!=1 if k=='social_checked' else d[k] is None)
            if bad:out[k]+=1
    return {k:v for k,v in out.items() if v}

def build(c):
    now=int(time.time()); v2_setup(c)
    session=session_started_at(c)
    window_cutoff=now-ACTIVE_SECONDS
    cutoff=max(window_cutoff,session or window_cutoff)
    try:h=c.execute('SELECT updated,message FROM v2_health WHERE id=1').fetchone()
    except sqlite3.OperationalError:h=None
    if h:
        age=max(0,now-int(h[0])); engine=('🟢 Running' if age<=30 else ('🟡 Stale' if age<=120 else '🔴 Stale'))+f' · {age}s ago'
    else:engine='🔴 No tracker report'
    public='🟢 ON' if os.environ.get('PUBLIC_ALERTS_ENABLED','false').lower()=='true' else '🔴 OFF'
    scope=f'last {ACTIVE_SECONDS//60}m'
    if session and session>window_cutoff: scope+=f' · session {max(0,now-session)//60}m old'
    lines=['TRENCHNET V2 — PRIVATE TEST','',f'Engine: {engine}',f'Public delivery: {public}','Bonding gate: ≥60% mandatory',f'Active window: {scope}','']

    total_tracking=total_wait=total_ready=0
    health_tables={'flap':'scanner_health','stonk':'stonk_health','pons':'pons_health','embercurve':'ember_health','pumpfun':'pumpfun_health'}
    health_limits={'flap':(60,180),'stonk':(60,180),'pons':(60,180),'embercurve':(60,180),'pumpfun':(30,90)}
    for pad,label in PADS:
        # Tracking is a live working-set count. Crossed/awaiting/ready are strictly session/window scoped.
        tracking=_one(c,"SELECT COUNT(*) FROM v2_intelligence WHERE launchpad=? AND state='tracking' AND updated_at>=?",(pad,window_cutoff))
        crossed=_one(c,"SELECT COUNT(*) FROM v2_intelligence WHERE launchpad=? AND crossed_90_at>=?",(pad,cutoff))
        waiting=_one(c,"SELECT COUNT(*) FROM v2_intelligence WHERE launchpad=? AND state='awaiting_intelligence' AND crossed_90_at>=?",(pad,cutoff))
        ready=_one(c,"SELECT COUNT(*) FROM v2_intelligence WHERE launchpad=? AND state IN ('ready','alerted') AND crossed_90_at>=?",(pad,cutoff))
        errors=_one(c,"SELECT COUNT(*) FROM v2_intelligence WHERE launchpad=? AND crossed_90_at>=? AND last_error<>''",(pad,cutoff))
        total_tracking+=tracking; total_wait+=waiting; total_ready+=ready
        g,y=health_limits[pad]
        lines += [f'{label.upper()}  {_health(c,health_tables[pad],g,y)}',f'Tracking <60%: {tracking} · Crossed 60%: {crossed}',f'Awaiting intel: {waiting} · Ready: {ready} · Errors: {errors}','']

    missing=_missing(c,cutoff)
    lines += ['STAGE 2',f'Below 60% / tracking: {total_tracking}',f'Awaiting intelligence: {total_wait}',f'Ready: {total_ready}']
    if missing:
        pretty={'description':'description','social_checked':'social check','holder_count':'holders','top10_holder_pct':'top 10','sniper_count':'sniper count','sniper_concentration_pct':'sniper concentration','buy_count':'buys','sell_count':'sells','unique_buyers':'unique buyers','unique_sellers':'unique sellers','volume':'volume'}
        lines.append('Missing: '+', '.join(f'{pretty[k]}={v}' for k,v in missing.items()))
    else:lines.append('Missing: none in active awaiting set')
    # Collector-level diagnostics make Stage 2 failures actionable.
    try:
        cr=c.execute("""SELECT s.collector,s.status,COUNT(*) FROM v2_collector_state s
          JOIN v2_intelligence v ON v.event_key=s.event_key
          WHERE v.state='awaiting_intelligence' AND v.crossed_90_at>=?
          GROUP BY s.collector,s.status ORDER BY s.collector,s.status""",(cutoff,)).fetchall()
    except sqlite3.OperationalError:cr=[]
    if cr:
        lines.append('Collectors: '+', '.join(f'{a} {b}={n}' for a,b,n in cr))

    # A historical V1/global_outbox row can never appear here unless its token crossed
    # the V2 60% gate during this session/window. This fixes misleading lifetime Sent totals.
    try:
        states=c.execute("""SELECT o.state,COUNT(*) FROM global_outbox o
          JOIN v2_intelligence v ON v.event_key=o.event_key
          WHERE v.crossed_90_at>=? AND o.state IN ('pending','sent','v2_blocked','preference_blocked','stale','metadata_blocked')
          GROUP BY o.state""",(cutoff,)).fetchall()
    except sqlite3.OperationalError:states=[]
    sm=dict(states)
    lines += ['','DELIVERY SAFETY',f"Queued: {sm.get('pending',0)} · Sent: {sm.get('sent',0)}",f"V2 blocked: {sm.get('v2_blocked',0)} · Preference blocked: {sm.get('preference_blocked',0)}",f"Stale/replay: {sm.get('stale',0)} · Metadata blocked: {sm.get('metadata_blocked',0)}"]
    return '\n'.join(lines)
