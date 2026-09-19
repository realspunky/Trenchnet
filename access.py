"""Durable trial/paid access and logical alert reservations. All timestamps UTC."""
import calendar
import time
from datetime import datetime, timezone

PLANS = {'monthly': 5, 'yearly': 60, 'lifetime': 100}
DAY = 86400

def setup(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS access (
      user_id INTEGER PRIMARY KEY, trial_start INTEGER,
      paid_until INTEGER NOT NULL DEFAULT 0, lifetime INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS alerts (
      user_id INTEGER NOT NULL, event_key TEXT NOT NULL,
      trial_day INTEGER, created INTEGER NOT NULL,
      PRIMARY KEY(user_id, event_key));
    CREATE UNIQUE INDEX IF NOT EXISTS trial_daily ON alerts(user_id, trial_day)
      WHERE trial_day IS NOT NULL;
    CREATE TABLE IF NOT EXISTS charges (
      charge_id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, plan TEXT NOT NULL);
    ''')
    c.commit()

def now_value(now):
    return int(time.time()) if now is None else int(now)

def start_trial(c, user_id, now=None):
    now = now_value(now)
    with c:
        c.execute('INSERT OR IGNORE INTO access(user_id) VALUES (?)', (user_id,))
        changed = c.execute('UPDATE access SET trial_start=? WHERE user_id=? AND trial_start IS NULL',
                            (now, user_id)).rowcount
    return bool(changed)

def state(c, user_id, now=None):
    now = now_value(now)
    row = c.execute('SELECT trial_start,paid_until,lifetime FROM access WHERE user_id=?', (user_id,)).fetchone()
    if not row:
        return 'inactive', None
    start, paid, lifetime = row
    if lifetime:
        return 'lifetime', None
    if paid > now:
        return 'paid', paid
    if start is not None and start <= now < start + 5 * DAY:
        return 'trial', start + 5 * DAY
    return 'expired', None

def reserve_alert(c, user_id, event_key, now=None):
    """One logical event reservation feeds BOTH delivery channels.

    Caller must use a stable chain:address:launch or chain:address:bonding key.
    False means no access, daily cap, or already reserved. Persisted reservations
    are not deliveries: a future durable worker must retry channels on the same
    reservation, never reserve again for email or a retry.
    """
    import sqlite3
    now = now_value(now)
    try:
        with c:
            c.execute('BEGIN IMMEDIATE')
            kind, _ = state(c, user_id, now)
            if kind not in {'trial', 'paid', 'lifetime'}:
                return False
            day = None
            if kind == 'trial':
                start = c.execute('SELECT trial_start FROM access WHERE user_id=?', (user_id,)).fetchone()[0]
                day = (now - start) // DAY
            c.execute('INSERT INTO alerts VALUES (?,?,?,?)', (user_id, event_key, day, now))
        return True
    except sqlite3.IntegrityError:
        return False

def grant_verified_payment(c, user_id, plan, charge_id, now=None):
    """INTERNAL ONLY. Future payment handler must verify Telegram successful_payment
    currency, amount, invoice ownership and payload before calling this function.
    Never expose this as a user command. Charge replay is rejected.
    """
    if plan not in PLANS or not charge_id:
        raise ValueError('Invalid plan or charge')
    now = now_value(now)
    with c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT 1 FROM charges WHERE charge_id=?', (charge_id,)).fetchone():
            return False
        c.execute('INSERT OR IGNORE INTO access(user_id) VALUES (?)', (user_id,))
        paid, lifetime = c.execute('SELECT paid_until,lifetime FROM access WHERE user_id=?', (user_id,)).fetchone()
        if lifetime:
            raise ValueError('Already lifetime: payment requires review/refund')
        until = paid
        if plan != 'lifetime':
            d = datetime.fromtimestamp(max(now, paid), timezone.utc)
            months = 1 if plan == 'monthly' else 12
            index = d.year * 12 + d.month - 1 + months
            year, month = divmod(index, 12)
            until = int(d.replace(year=year, month=month+1,
                       day=min(d.day, calendar.monthrange(year, month+1)[1])).timestamp())
        c.execute('UPDATE access SET paid_until=?,lifetime=? WHERE user_id=?',
                  (until, int(plan == 'lifetime'), user_id))
        c.execute('INSERT INTO charges VALUES (?,?,?)', (charge_id, user_id, plan))
    return True
