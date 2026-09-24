"""V2 tracker: refreshes the mandatory 60% gate and Stage-2 enrichment.

Adapters are deliberately source-driven. If a launchpad does not expose a fact
reliably, the token stays awaiting_intelligence rather than receiving a fabricated value.
"""
import json, os, sqlite3, time, urllib.request
from v2_intelligence import setup, mark_progress, upsert_intelligence, complete, extract, start_session, stage2_required
from v2_adapters import fetch as adapter_fetch
from launch_model import social_links

def _json_url(url):
    req=urllib.request.Request(url,headers={"Accept":"application/json","User-Agent":"TrenchNet-V2/2.0"})
    with urllib.request.urlopen(req,timeout=15) as r:
        raw=r.read(2_000_001)
    if len(raw)>2_000_000:raise ValueError("V2 intelligence response too large")
    return json.loads(raw)

def refresh_from_stored(c,row,now):
    event_key,launchpad,address,launched_at,bonding,migrated,raw=row
    try:meta=json.loads(raw or "{}")
    except Exception:meta={}
    meta.setdefault('launched_at',launched_at)
    adapted=adapter_fetch(launchpad,address,meta)
    if adapted:
        bonding,remote=adapted
        merged=dict(meta); merged.update(remote); meta=merged
        sx,web=social_links(meta)
        with c:c.execute("""UPDATE unified_launches SET bonding_progress=?,metadata=?,last_seen=?,
                         social_x_url=CASE WHEN ?<>'' THEN ? ELSE social_x_url END,
                         website_url=CASE WHEN ?<>'' THEN ? ELSE website_url END WHERE event_key=?""",
                         (bonding,json.dumps(meta,separators=(',',':'),default=str),now,sx,sx,web,web,event_key))
    crossed=mark_progress(c,event_key,address,launchpad,bonding,launched_at,bool(migrated),now)
    if not crossed:return False
    # Isolated delivery test mode: once verified bonding crosses 60%, promote
    # directly to intake. Stage 2 collectors are intentionally skipped.
    if not stage2_required():
        return True
    # Stage 2 is launchpad-specific underneath but normalized here. This call was
    # previously missing from the tracker, which meant Ember/STOnK/Flap could cross
    # the gate without ever running the shared native/public collectors.
    if launchpad != "pons":
        try:
            from stage2_collectors import enrich
            meta=enrich(launchpad,address,meta)
        except Exception as e:
            meta['stage2_enrich_error']=type(e).__name__+': '+str(e)[:120]
    # V2 Stage 2 uses launchpad-native/public collectors only.
    return upsert_intelligence(c,event_key,address,launchpad,meta,source="verified_post60_stage2",now=now)

def promote(c,event_key,ready):
    with c:
        c.execute("UPDATE unified_launches SET pipeline_state=? WHERE event_key=?",
                  ("intake" if ready else "awaiting_intelligence",event_key))


def _health_touch(c, message="V2 tracker working"):
    ts=int(time.time())
    with c:
        c.execute("CREATE TABLE IF NOT EXISTS v2_health(id INTEGER PRIMARY KEY CHECK(id=1),updated INTEGER,message TEXT)")
        c.execute("INSERT OR REPLACE INTO v2_health VALUES(1,?,?)",(ts,str(message)[:240]))

def _tracking_rows(c, now, limit, retry_delay):
    awaiting=c.execute("""SELECT u.event_key,u.launchpad,u.address,u.launched_at,u.bonding_progress,u.migrated,u.metadata
      FROM unified_launches u LEFT JOIN v2_intelligence v ON v.event_key=u.event_key
      WHERE u.pipeline_state='awaiting_intelligence' AND COALESCE(v.updated_at,0)<=?
      ORDER BY COALESCE(v.updated_at,0) ASC LIMIT ?""",(now-retry_delay,limit)).fetchall()
    remaining=max(0,limit-len(awaiting))
    if remaining<=0:return awaiting
    pads=("flap","stonk","pons","embercurve","pumpfun")
    default_quota=max(1,remaining//len(pads))
    rows=list(awaiting); seen={r[0] for r in rows}
    for pad in pads:
        envkey="V2_TRACK_"+pad.upper().replace(".","")+"_BATCH"
        quota=int(os.environ.get(envkey,"10" if pad=="pons" else str(default_quota)))
        quota=max(1,min(quota,remaining))
        part=c.execute("""SELECT u.event_key,u.launchpad,u.address,u.launched_at,u.bonding_progress,u.migrated,u.metadata
          FROM unified_launches u LEFT JOIN v2_intelligence v ON v.event_key=u.event_key
          WHERE u.pipeline_state='v2_tracking' AND u.launchpad=?
          ORDER BY COALESCE(u.bonding_progress,-1) DESC, COALESCE(v.updated_at,0) ASC, u.last_seen DESC
          LIMIT ?""",(pad,quota)).fetchall()
        for r in part:
            if r[0] not in seen: rows.append(r);seen.add(r[0])
    return rows[:limit]


def cycle(c,now=None,limit=None):
    setup(c);now=int(time.time() if now is None else now)
    limit=int(os.environ.get("V2_TRACK_BATCH","250") if limit is None else limit)
    retry_delay=max(5,int(os.environ.get("V2_INTELLIGENCE_RETRY_SECONDS","20")))
    rows=_tracking_rows(c,now,limit,retry_delay)
    ready=waiting=tracking=0
    _health_touch(c,f"V2 cycle started: {len(rows)} scheduled")
    for idx,row in enumerate(rows,1):
        if idx==1 or idx%5==0:_health_touch(c,f"V2 working: {idx}/{len(rows)} · {row[1]}")
        event_key=row[0]
        try:
            ok=refresh_from_stored(c,row,now)
        except Exception as e:
            with c:
                c.execute("UPDATE v2_intelligence SET updated_at=?,last_error=? WHERE event_key=?",
                          (now,(type(e).__name__+': '+str(e))[:180],event_key))
            waiting+=1
            continue
        intel=c.execute("SELECT crossed_90_at,state FROM v2_intelligence WHERE event_key=?",(event_key,)).fetchone()
        if not intel or intel[0] is None:
            tracking+=1;continue
        if ok:
            promote(c,event_key,True);ready+=1
        else:
            promote(c,event_key,False);waiting+=1
    return {"processed":len(rows),"ready":ready,"waiting":waiting,"tracking":tracking}

def run():
    if os.environ.get("TRENCHNET_V2_ENABLED","false").lower()!="true":return
    from bot import database
    c=database();setup(c);start_session(c)
    print("TrenchNet V2 tracker started.",flush=True)
    _health_touch(c,"V2 tracker started")
    while True:
        try:
            _health_touch(c,"V2 tracker scheduling")
            r=cycle(c)
            _health_touch(c,f"V2: {r['processed']} checked; {r['ready']} ready; {r['waiting']} awaiting; {r['tracking']} below 60%")
        except Exception as e:
            _health_touch(c,"V2 tracker error: "+type(e).__name__+": "+str(e)[:160])
            print("V2 tracker error: "+type(e).__name__+": "+str(e)[:160],flush=True)
        time.sleep(float(os.environ.get("V2_TRACK_POLL_SECONDS","5")))

if __name__=="__main__":run()
