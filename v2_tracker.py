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
    # Heavy intelligence is strictly post-60. Authenticated Binance is optional enrichment only;
    # native/launchpad collectors remain authoritative and missing facts stay fail-closed.
    try:
        from binance_web3_v2 import fetch as binance_advanced
        extra=binance_advanced(launchpad,address)
        if extra:
            merged=dict(meta)
            for k,v in extra.items():
                if isinstance(v,dict) and isinstance(merged.get(k),dict):
                    merged[k]={**merged[k],**v}
                else: merged[k]=v
            meta=merged
    except Exception as e:
        # Do not destroy native intelligence when Binance is unavailable/rate-limited.
        meta['binance_advanced_error']=type(e).__name__
    return upsert_intelligence(c,event_key,address,launchpad,meta,source="verified_post60_stage2",now=now)

def promote(c,event_key,ready):
    with c:
        c.execute("UPDATE unified_launches SET pipeline_state=? WHERE event_key=?",
                  ("intake" if ready else "awaiting_intelligence",event_key))

def cycle(c,now=None,limit=None):
    setup(c);now=int(time.time() if now is None else now)
    limit=int(os.environ.get("V2_TRACK_BATCH","250") if limit is None else limit)
    retry_delay=max(5,int(os.environ.get("V2_INTELLIGENCE_RETRY_SECONDS","20")))
    rows=c.execute("""SELECT u.event_key,u.launchpad,u.address,u.launched_at,u.bonding_progress,u.migrated,u.metadata
      FROM unified_launches u LEFT JOIN v2_intelligence v ON v.event_key=u.event_key
      WHERE u.pipeline_state='v2_tracking'
         OR (u.pipeline_state='awaiting_intelligence' AND COALESCE(v.updated_at,0)<=?)
      ORDER BY CASE WHEN u.pipeline_state='awaiting_intelligence' THEN 0 ELSE 1 END,
               CASE WHEN u.pipeline_state='awaiting_intelligence' THEN u.launched_at ELSE -u.last_seen END ASC
      LIMIT ?""",(now-retry_delay,limit)).fetchall()
    ready=waiting=tracking=0
    for row in rows:
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
    while True:
        try:
            r=cycle(c)
            with c:
                c.execute("""CREATE TABLE IF NOT EXISTS v2_health(id INTEGER PRIMARY KEY CHECK(id=1),updated INTEGER,message TEXT)""")
                c.execute("INSERT OR REPLACE INTO v2_health VALUES(1,?,?)",(int(time.time()),f"V2: {r['processed']} checked; {r['ready']} ready; {r['waiting']} awaiting intelligence; {r['tracking']} below 60%"))
        except Exception as e:
            print("V2 tracker error: "+type(e).__name__+": "+str(e)[:160],flush=True)
        time.sleep(float(os.environ.get("V2_TRACK_POLL_SECONDS","5")))

if __name__=="__main__":run()
