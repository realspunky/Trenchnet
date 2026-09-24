"""Verified Stage-2 adapter helpers.

Operators can provide a public/read-only JSON endpoint template per launchpad.
The response must contain explicit bonding progress plus Stage-2 fields; TrenchNet
validates rather than inventing missing data.
Template example: https://provider.example/token/{address}
"""
import os
from urllib.parse import quote
import json, urllib.request

def _json_url(url):
    req=urllib.request.Request(url,headers={'Accept':'application/json','User-Agent':'TrenchNet-V2/2.0'})
    with urllib.request.urlopen(req,timeout=15) as r: raw=r.read(2_000_001)
    if len(raw)>2_000_000: raise ValueError('V2 adapter response too large')
    return json.loads(raw)
from v2_intelligence import normalize_progress

def endpoint(launchpad,address):
    key="V2_"+launchpad.upper().replace(".","").replace("-","_")+"_INTELLIGENCE_URL"
    tpl=os.environ.get(key,"").strip()
    if not tpl:return None
    return tpl.replace("{address}",quote(address,safe=""))

def fetch(launchpad,address,metadata=None):
    # First-party/native adapters. All fail closed on unavailable verification.
    if launchpad == "pons":
        try:
            from pons_v2_intelligence import fetch as pons_fetch
            return pons_fetch(address, metadata)
        except Exception:
            pass
    if launchpad == "pumpfun":
        try:
            from pump_v2_intelligence import fetch as pump_fetch
            result=pump_fetch(address)
            if result:
                p,data=result
                merged=dict(metadata or {}); merged.update(data or {})
                from stage2_collectors import enrich
                return (p,enrich(launchpad,address,merged)) if p>=60 else (p,merged)
        except Exception:
            pass
    if launchpad in {"flap","stonk","embercurve"}:
        try:
            from platform_v2_intelligence import fetch as native_fetch
            result=native_fetch(launchpad,address,metadata)
            if result:return result
        except Exception:
            pass
    url=endpoint(launchpad,address)
    if not url:return None
    data=_json_url(url)
    if not isinstance(data,dict):raise ValueError("V2 adapter must return JSON object")
    p=None
    for k in ("bondingProgress","bonding_progress","progress","curveProgress"):
        if data.get(k) is not None:p=normalize_progress(data[k]);break
    if p is None:raise ValueError("V2 adapter missing verified bonding progress")
    return p,data
