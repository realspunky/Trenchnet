"""TrenchNet V2 qualification/intelligence layer.

V2 is fail-closed:
- a token cannot become alert-eligible before verified bonding progress >= 60%
- Stage 2 intelligence must be complete before the global filter can approve it
- unavailable facts remain unavailable; TrenchNet never fabricates zeros or socials
"""
import json, os, time

V2_MIN_BONDING = 60.0
REQUIRED = (
    "description","social_checked","holder_count","top10_holder_pct",
    "sniper_count","sniper_concentration_pct","buy_count","sell_count",
    "unique_buyers","unique_sellers","volume"
)

def setup(c):
    c.executescript("""
    CREATE TABLE IF NOT EXISTS v2_intelligence(
      event_key TEXT PRIMARY KEY,
      address TEXT NOT NULL,
      launchpad TEXT NOT NULL,
      crossed_90_at INTEGER,
      updated_at INTEGER NOT NULL,
      state TEXT NOT NULL DEFAULT 'tracking',
      description TEXT NOT NULL DEFAULT '',
      social_present INTEGER,
      social_checked INTEGER,
      holder_count INTEGER,
      top10_holder_pct REAL,
      dev_holding_pct REAL,
      dev_total_launches INTEGER,
      dev_migrated_count INTEGER,
      dev_funding_source TEXT NOT NULL DEFAULT '',
      sniper_count INTEGER,
      sniper_concentration_pct REAL,
      largest_sniper_pct REAL,
      sniper_still_holding INTEGER,
      sniper_sold INTEGER,
      bundled_wallet_count INTEGER,
      buy_count INTEGER,
      sell_count INTEGER,
      unique_buyers INTEGER,
      unique_sellers INTEGER,
      buy_volume REAL,
      sell_volume REAL,
      volume REAL,
      volume_asset TEXT NOT NULL DEFAULT 'USD',
      window_seconds INTEGER,
      launch_to_90_seconds INTEGER,
      source TEXT NOT NULL DEFAULT '',
      raw TEXT NOT NULL DEFAULT '{}',
      last_error TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS v2_state_idx ON v2_intelligence(state,updated_at);
    CREATE TABLE IF NOT EXISTS v2_runtime(
      id INTEGER PRIMARY KEY CHECK(id=1),
      session_started_at INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS v2_collector_state(
      event_key TEXT NOT NULL,
      collector TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending',
      attempts INTEGER NOT NULL DEFAULT 0,
      updated_at INTEGER NOT NULL,
      last_error TEXT NOT NULL DEFAULT '',
      PRIMARY KEY(event_key,collector)
    );
    CREATE INDEX IF NOT EXISTS v2_collector_status_idx ON v2_collector_state(status,updated_at);
    """)
    # Forward-compatible migration for persistent /data databases.
    cols={r[1] for r in c.execute("PRAGMA table_info(v2_intelligence)").fetchall()}
    migrations={"social_checked":"INTEGER","dev_total_launches":"INTEGER","dev_migrated_count":"INTEGER","dev_funding_source":"TEXT NOT NULL DEFAULT ''","volume_asset":"TEXT NOT NULL DEFAULT 'USD'"}
    for name,typ in migrations.items():
        if name not in cols:c.execute(f"ALTER TABLE v2_intelligence ADD COLUMN {name} {typ}")
    c.commit()

def start_session(c, now=None):
    """Record this Railway V2 process start without touching historical token rows."""
    setup(c); now=int(time.time() if now is None else now)
    with c:
        c.execute("INSERT OR REPLACE INTO v2_runtime(id,session_started_at) VALUES(1,?)",(now,))
    return now

def session_started_at(c):
    setup(c)
    r=c.execute("SELECT session_started_at FROM v2_runtime WHERE id=1").fetchone()
    return int(r[0]) if r and r[0] is not None else None

def enabled():
    return os.environ.get("TRENCHNET_V2_ENABLED","false").lower()=="true"

def stage2_required():
    """Whether Stage 2 intelligence is a delivery requirement.

    Test-only bypass: bonding verification remains mandatory.
    """
    return os.environ.get("STAGE2_REQUIRED","true").strip().lower() not in {"0","false","no","off"}

def normalize_progress(value):
    try:
        x=float(value)
    except (TypeError,ValueError):
        return None
    if 0 <= x <= 1: x*=100
    if not 0 <= x <= 100: return None
    return x

def bonding_gate(progress, migrated=False):
    p=normalize_progress(progress)
    # Graduated is equivalent to a completed curve only when the scanner explicitly
    # verified that status; otherwise missing progress remains fail-closed.
    if migrated and p is None: return 100.0
    return p if p is not None and p >= V2_MIN_BONDING else None

def mark_progress(c,event_key,address,launchpad,progress,launched_at=None,migrated=False,now=None):
    setup(c); now=int(time.time() if now is None else now)
    p=bonding_gate(progress,migrated)
    row=c.execute("SELECT crossed_90_at,state FROM v2_intelligence WHERE event_key=?",(event_key,)).fetchone()
    crossed=(row[0] if row else None)
    state=(row[1] if row else "tracking")
    if p is not None and crossed is None:
        crossed=now
        state="awaiting_intelligence"
    with c:
        c.execute("""INSERT INTO v2_intelligence(event_key,address,launchpad,crossed_90_at,updated_at,state,launch_to_90_seconds)
          VALUES(?,?,?,?,?,?,?)
          ON CONFLICT(event_key) DO UPDATE SET crossed_90_at=COALESCE(v2_intelligence.crossed_90_at,excluded.crossed_90_at),
          updated_at=excluded.updated_at,
          state=CASE WHEN v2_intelligence.state IN ('ready','alerted') THEN v2_intelligence.state ELSE excluded.state END,
          launch_to_90_seconds=COALESCE(v2_intelligence.launch_to_90_seconds,excluded.launch_to_90_seconds)""",
          (event_key,address,launchpad,crossed,now,state,
           max(0,crossed-int(launched_at)) if crossed and launched_at else None))
    return p is not None

def _num(v, integer=False):
    if v is None:return None
    try:return int(v) if integer else float(v)
    except (TypeError,ValueError):return None

def _pick(d,*keys):
    for k in keys:
        if isinstance(d,dict) and d.get(k) is not None:return d[k]
    return None

def _coalesce(*values):
    """First non-None value. Unlike `or`, preserves valid zero metrics."""
    for v in values:
        if v is not None:return v
    return None

def extract(metadata):
    """Extract only source-supplied intelligence. Missing data stays missing."""
    m=metadata if isinstance(metadata,dict) else {}
    stats=_pick(m,"stats","market","analytics","metrics") or {}
    holders=_pick(m,"holders","holderStats","holder_stats") or {}
    snipers=_pick(m,"snipers","sniperStats","sniper_stats") or {}
    trades=_pick(m,"trades","tradeStats","trade_stats") or {}
    desc=str(_pick(m,"description","desc","tokenDescription") or "").strip()[:600]
    developer=_pick(m,"developer","devInfo","dev_info") or {}
    social_keys=("twitter","x","x_url","twitter_url","website","website_url","telegram")
    social=bool(_pick(m,*social_keys))
    social_checked=bool(m.get("social_checked") or m.get("binance_web3") or any(k in m for k in social_keys))
    return {
      "description":desc,
      "social_present":int(social),
      "social_checked":int(social_checked),
      "holder_count":_num(_coalesce(_pick(holders,"count","holderCount","holders"),_pick(m,"holderCount","holder_count")),True),
      "top10_holder_pct":_num(_coalesce(_pick(holders,"top10Pct","top10_percent","top10_holder_pct"),_pick(m,"top10_holder_pct"))),
      "dev_holding_pct":_num(_coalesce(_pick(holders,"devPct","creatorPct","dev_holding_pct"),_pick(m,"dev_holding_pct"))),
      "dev_total_launches":_num(_pick(developer,"totalLaunched","totalToken"),True),
      "dev_migrated_count":_num(_pick(developer,"migratedCount","migrated_count"),True),
      "dev_funding_source":str(_pick(developer,"fundingSourceLabel","fundingSource") or "")[:160],
      "sniper_count":_num(_coalesce(_pick(snipers,"count","sniperCount"),_pick(m,"sniper_count")),True),
      "sniper_concentration_pct":_num(_coalesce(_pick(snipers,"concentrationPct","combinedPct","sniper_concentration_pct"),_pick(m,"sniper_concentration_pct"))),
      "largest_sniper_pct":_num(_coalesce(_pick(snipers,"largestPct","largest_sniper_pct"),_pick(m,"largest_sniper_pct"))),
      "sniper_still_holding":_num(_pick(snipers,"stillHolding","still_holding"),True),
      "sniper_sold":_num(_pick(snipers,"sold","soldCount"),True),
      "bundled_wallet_count":_num(_pick(m,"bundled_wallet_count","bundleCount"),True),
      "buy_count":_num(_coalesce(_pick(trades,"buys","buyCount"),_pick(stats,"buys","buyCount"),_pick(m,"buy_count")),True),
      "sell_count":_num(_coalesce(_pick(trades,"sells","sellCount"),_pick(stats,"sells","sellCount"),_pick(m,"sell_count")),True),
      "unique_buyers":_num(_coalesce(_pick(trades,"uniqueBuyers","unique_buyers"),_pick(m,"unique_buyers")),True),
      "unique_sellers":_num(_coalesce(_pick(trades,"uniqueSellers","unique_sellers"),_pick(m,"unique_sellers")),True),
      "buy_volume":_num(_coalesce(_pick(trades,"buyVolume","buy_volume"),_pick(stats,"buyVolume","buy_volume"))),
      "sell_volume":_num(_coalesce(_pick(trades,"sellVolume","sell_volume"),_pick(stats,"sellVolume","sell_volume"))),
      "volume":_num(_coalesce(_pick(trades,"volume","volumeUsd","volume_usd"),_pick(stats,"volume","volumeUsd","volume_usd"),_pick(m,"volume"))),
      "volume_asset":str(_pick(m,"volume_asset") or "USD")[:24],
      "window_seconds":_num(_coalesce(_pick(trades,"windowSeconds","window_seconds"),_pick(stats,"windowSeconds","window_seconds")),True),
    }

COLLECTOR_FIELDS = {
    "metadata": ("description",),
    "socials": ("social_checked",),
    "holders": ("holder_count","top10_holder_pct"),
    "trading": ("buy_count","sell_count","unique_buyers","unique_sellers","volume"),
    "snipers": ("sniper_count","sniper_concentration_pct"),
}

def _collector_status(intel, metadata, collector):
    fields=COLLECTOR_FIELDS[collector]
    ok=True
    for k in fields:
        v=intel.get(k)
        if k=="description": ok=ok and bool(str(v or "").strip())
        elif k=="social_checked": ok=ok and v==1
        else: ok=ok and v is not None
    if ok:return "verified",""
    unavailable=metadata.get(collector+"_unavailable")
    if unavailable:return "unavailable",str(unavailable)[:180]
    # Preserve source errors as retryable errors, not fake unavailable values.
    error_keys={
      "metadata":("metadata_error","pons_native_error"),
      "socials":("social_error","public_market_error","pons_native_error"),
      "holders":("holder_error","pons_holder_error","native_chain_error"),
      "trading":("trade_error","pons_trade_error","pons_native_error","native_chain_error"),
      "snipers":("sniper_error","pons_trade_error","pons_native_error","native_chain_error"),
    }[collector]
    for k in error_keys:
        if metadata.get(k):return "error",str(metadata.get(k))[:180]
    return "pending",""

def update_collector_states(c,event_key,intel,metadata,now):
    for collector in COLLECTOR_FIELDS:
        status,err=_collector_status(intel,metadata,collector)
        c.execute("""INSERT INTO v2_collector_state(event_key,collector,status,attempts,updated_at,last_error)
          VALUES(?,?,?,?,?,?) ON CONFLICT(event_key,collector) DO UPDATE SET
          status=excluded.status,attempts=v2_collector_state.attempts+1,updated_at=excluded.updated_at,last_error=excluded.last_error""",
          (event_key,collector,status,1,now,err))

def collectors_complete(c,event_key):
    rows=c.execute("SELECT collector,status FROM v2_collector_state WHERE event_key=?",(event_key,)).fetchall()
    d=dict(rows)
    return all(d.get(k) in {"verified","unavailable"} for k in COLLECTOR_FIELDS)

def complete(intel):
    if not intel.get("description"):return False
    if intel.get("social_checked") != 1:return False
    for k in REQUIRED:
        if k in {"description","social_checked"}:continue
        if intel.get(k) is None:return False
    return True

def upsert_intelligence(c,event_key,address,launchpad,metadata,source="",now=None):
    setup(c);now=int(time.time() if now is None else now);intel=extract(metadata)
    cols=list(intel)
    assigns=",".join(f"{k}=excluded.{k}" for k in cols)
    vals=[intel[k] for k in cols]
    with c:
        # Collector states are written before readiness is decided so status can explain exactly why a token is waiting.
        update_collector_states(c,event_key,intel,metadata or {},now)
        is_ready=complete(intel) or collectors_complete(c,event_key)
        c.execute(f"""INSERT INTO v2_intelligence(event_key,address,launchpad,updated_at,state,{','.join(cols)},source,raw)
          VALUES(?,?,?,?,?,{','.join('?' for _ in cols)},?,?)
          ON CONFLICT(event_key) DO UPDATE SET updated_at=excluded.updated_at,{assigns},source=excluded.source,raw=excluded.raw,
          state=CASE WHEN v2_intelligence.crossed_90_at IS NULL THEN 'tracking'
                     WHEN excluded.state='ready' THEN 'ready' ELSE 'awaiting_intelligence' END""",
          [event_key,address,launchpad,now,"ready" if is_ready else "awaiting_intelligence",*vals,source,
           json.dumps(metadata or {},separators=(",",":"),default=str)])
    return is_ready

def gate(c,event_key,bonding,migrated=False):
    if not enabled():return True,"v2_disabled"
    if bonding_gate(bonding,migrated) is None:return False,"bonding_below_60"
    # During isolated delivery testing Stage 2 may be bypassed, but the bonding
    # gate above is NEVER bypassed.
    if not stage2_required():return True,"stage2_bypassed"
    setup(c)
    r=c.execute("SELECT state FROM v2_intelligence WHERE event_key=?",(event_key,)).fetchone()
    if not r or r[0]!="ready":return False,"intelligence_incomplete"
    return True,"v2_ready"

def render(c,event_key):
    if enabled() and not stage2_required():
        return ["","🧪 STAGE 2 VERIFICATION BYPASSED","⚠️ Delivery test only — bonding ≥60% is still mandatory."]
    setup(c);c.row_factory=None
    r=c.execute("""SELECT description,holder_count,top10_holder_pct,dev_holding_pct,dev_total_launches,dev_migrated_count,dev_funding_source,sniper_count,
      sniper_concentration_pct,largest_sniper_pct,sniper_still_holding,sniper_sold,bundled_wallet_count,
      buy_count,sell_count,unique_buyers,unique_sellers,buy_volume,sell_volume,volume,volume_asset,window_seconds,
      launch_to_90_seconds FROM v2_intelligence WHERE event_key=?""",(event_key,)).fetchone()
    if not r:return []
    (desc,holders,top10,dev,devlaunch,devmigrated,devfund,snipers,sconc,largest,still,sold,bundles,buys,sells,ub,us,bv,sv,vol,volasset,window,t90)=r
    lines=["","🧠 STAGE 2 INTELLIGENCE",f"📝 {desc}"]
    lines += [f"👥 Holders: {holders} | Top 10: {top10:.2f}%",f"👨‍💻 Dev holding: {dev:.2f}%" if dev is not None else "👨‍💻 Dev holding: unavailable"]
    if devlaunch is not None:
        lines.append(f"🧑‍💻 Dev launches: {devlaunch}" + (f" | Migrated: {devmigrated}" if devmigrated is not None else ""))
    if devfund:lines.append(f"💳 Dev funding source: {devfund}")
    lines += [f"🎯 Snipers: {snipers} | Combined: {sconc:.2f}% | Largest: {largest:.2f}%" if largest is not None else f"🎯 Snipers: {snipers} | Combined: {sconc:.2f}%"]
    if still is not None and sold is not None:lines.append(f"🔎 Snipers holding/sold: {still}/{sold}")
    if bundles is not None:lines.append(f"🔗 Bundled/linked wallets: {bundles}")
    activity=f"🟢 Buys: {buys}" + (f" ({ub} unique)" if ub is not None else "") + f" | 🔴 Sells: {sells}" + (f" ({us} unique)" if us is not None else "")
    vlabel=f"${vol:,.2f}" if (volasset or "USD").upper()=="USD" else f"{vol:,.4f} {volasset}"
    lines += [activity,f"💵 Volume: {vlabel} / recent window"]
    if bv is not None and sv is not None:lines.append(f"↕️ Buy/Sell volume: {bv:,.2f} / {sv:,.2f}")
    if window:lines.append(f"⏱️ Activity window: {window//60}m")
    if t90 is not None:lines.append(f"🚀 Launch → 60%: {t90//60}m {t90%60}s")
    return lines
