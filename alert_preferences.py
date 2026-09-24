"""Per-user launchpad alert preferences for TrenchNet."""
LAUNCHPADS=('flap','stonk','pons','embercurve','pumpfun')
LABELS={'flap':'Flap','stonk':'STOnK','pons':'PONS','embercurve':'EmberCurve','pumpfun':'Pump.fun'}

def setup(c):
    c.execute('''CREATE TABLE IF NOT EXISTS user_launchpad_preferences(
      user_id INTEGER NOT NULL, launchpad TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
      PRIMARY KEY(user_id,launchpad))''')
    c.commit()

def ensure_user(c,user_id):
    setup(c)
    with c:
        for pad in LAUNCHPADS:
            c.execute('INSERT OR IGNORE INTO user_launchpad_preferences(user_id,launchpad,enabled) VALUES(?,?,1)',(user_id,pad))

def get(c,user_id):
    ensure_user(c,user_id)
    rows=dict(c.execute('SELECT launchpad,enabled FROM user_launchpad_preferences WHERE user_id=?',(user_id,)).fetchall())
    return {p:bool(rows.get(p,1)) for p in LAUNCHPADS}

def toggle(c,user_id,pad):
    if pad not in LAUNCHPADS: raise ValueError('unknown launchpad')
    ensure_user(c,user_id)
    with c:
        c.execute('UPDATE user_launchpad_preferences SET enabled=1-enabled WHERE user_id=? AND launchpad=?',(user_id,pad))
    return get(c,user_id)[pad]

def set_all(c,user_id,enabled):
    ensure_user(c,user_id)
    with c:c.execute('UPDATE user_launchpad_preferences SET enabled=? WHERE user_id=?',(int(bool(enabled)),user_id))

def keyboard(c,user_id):
    prefs=get(c,user_id)
    rows=[]
    for pad in LAUNCHPADS:
        rows.append([{'text':f'{"✅" if prefs[pad] else "❌"} {LABELS[pad]}','callback_data':'alerts:toggle:'+pad}])
    all_on=all(prefs.values())
    rows.append([{'text':('🔕 Disable All' if all_on else '🔔 Enable All'),'callback_data':'alerts:all:' + ('off' if all_on else 'on')}])
    rows.append([{'text':'Done','callback_data':'alerts:done'}])
    return {'inline_keyboard':rows}

def summary(c,user_id):
    prefs=get(c,user_id)
    enabled=[LABELS[p] for p in LAUNCHPADS if prefs[p]]
    return 'Launchpad alerts: ' + (', '.join(enabled) if enabled else 'None')
