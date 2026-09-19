"""TrenchNet command bot. Public alerts and payment acceptance are disabled."""
import json
import os
import sqlite3
import time
import urllib.request
from access import setup, start_trial, state

DB = os.environ.get('DATABASE_PATH', 'trenchnet.sqlite3')

def database():
    c = sqlite3.connect(DB, timeout=30)
    c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, threshold INTEGER NOT NULL DEFAULT 80 CHECK(threshold BETWEEN 80 AND 95))')
    c.execute('CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value INTEGER)')
    c.commit()
    setup(c)
    return c

def qualifies(token):
    return (token.get('verified') is True
            and token.get('launchpad') in {'pons', 'flap', 'stonk'}
            and token.get('chain') in {'solana', 'bnb', 'robinhood'}
            and token.get('total_tax_bps') == 300
            and token.get('holder_rewards') is True)

def advance_due(token, threshold):
    progress = token.get('bonding_percent')
    return (qualifies(token) and token.get('migrated') is False
            and isinstance(progress, (int, float))
            and threshold <= progress < 100)

def reply(c, user_id, text):
    c.execute('INSERT OR IGNORE INTO users(id) VALUES (?)', (user_id,))
    c.commit()
    if text == 'Start Free Trial':
        text = '/trial'
    parts = text.split()
    cmd = parts[0].split('@')[0] if parts else ''
    if cmd in {'/start', '/help'}:
        return ('Welcome to TrenchNet. Currently in development; live alerts and payments are disabled.\n'
                '/trial — start a 5-day trial (one alert per day)\n'
                '/threshold 80 — set bonding threshold (80–95)\n'
                '/status — view settings\n/plans — planned pricing\n'
                '/email — email availability\n/delete_me — remove saved settings')
    if cmd == '/myid':
        return f'Your Telegram user ID: {user_id}'
    if cmd == '/trial':
        if os.environ.get('TRIALS_ENABLED') != 'true':
            return 'Trials will open when live monitoring is ready. Your five days have not started.'
        return ('Your five-day trial has started: up to one qualifying alert per 24-hour trial day.'
                if start_trial(c, user_id) else 'This account has already used or started its trial. Use /status or /plans.')
    if cmd == '/threshold':
        if len(parts) != 2 or not parts[1].isdigit() or not 80 <= int(parts[1]) <= 95:
            return 'Choose a whole number from 80 to 95. Example: /threshold 85'
        c.execute('UPDATE users SET threshold=? WHERE id=?', (int(parts[1]), user_id))
        c.commit()
        return f'Bonding threshold saved: {parts[1]}%. Live alerts are not active yet.'
    if cmd == '/status':
        threshold = c.execute('SELECT threshold FROM users WHERE id=?', (user_id,)).fetchone()[0]
        kind, expiry = state(c, user_id)
        expiry_text = time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(expiry)) if expiry else 'none'
        monitoring = 'Public alerts disabled'
        if str(user_id) == os.environ.get('ADMIN_CHAT_ID'):
            try:
                health = c.execute('SELECT updated,status FROM scanner_health WHERE id=1').fetchone()
            except sqlite3.OperationalError:
                health = None
            if health:
                age = max(0, int(time.time()) - health[0])
                monitoring += f'\n{health[1]}\nLast scanner update: {age}s ago'
                if age > 180: monitoring += ' (stale; check Railway logs)'
                counts = c.execute('SELECT state,COUNT(*) FROM pilot_outbox GROUP BY state').fetchall()
                tokens = c.execute('SELECT status,COUNT(*) FROM scan_tokens GROUP BY status').fetchall()
                monitoring += '\nTokens: ' + (', '.join(f'{k}={v}' for k,v in tokens) or 'none yet')
                monitoring += '\nPilot deliveries: ' + (', '.join(f'{k}={v}' for k,v in counts) or 'none yet')
            else:
                monitoring += '\nPrivate scanner has not reported yet'
        return f'Bonding threshold: {threshold}%\nAccess: {kind}\nExpiry: {expiry_text}\n{monitoring}'
    if cmd == '/plans':
        return ('Planned prices: $5 monthly / $60 for 12 months / $100 lifetime. '
                'Free trial: five days, up to one qualifying alert per day; no automatic charge. Checkout is disabled. Telegram requires Stars for digital subscriptions sold inside bots. '
                'Payment design and Stars pricing are not finalized. Do not send funds.')
    if cmd == '/email':
        return 'Optional verified email alerts are planned. Email collection is not enabled yet.'
    if cmd == '/delete_me':
        c.execute('DELETE FROM users WHERE id=?', (user_id,))
        c.commit()
        return 'Your settings have been deleted. Trial-use and payment records are retained to prevent repeat trials and payment reuse.'
    return 'Use /help to see available commands.'

def api(token, method, payload):
    req = urllib.request.Request('https://api.telegram.org/bot' + token + '/' + method,
                                 data=json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=40) as response:
        result = json.load(response)
    if not result.get('ok'):
        raise RuntimeError('Telegram rejected request')
    return result['result']

def main():
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if not token:
        raise SystemExit('Set TELEGRAM_BOT_TOKEN securely in the server environment.')
    c = database()
    while True:
        try:
            row = c.execute("SELECT value FROM state WHERE key='offset'").fetchone()
            offset = row[0] if row else 0
            updates = api(token, 'getUpdates', {'offset': offset, 'timeout': 25, 'allowed_updates': ['message']})
            for update in updates:
                msg = update.get('message', {})
                if msg.get('chat', {}).get('type') == 'private' and 'text' in msg:
                    result = reply(c, msg['from']['id'], msg['text'])
                    api(token, 'sendMessage', {'chat_id': msg['chat']['id'], 'text': result,
                        'reply_markup': {'keyboard': [[{'text': 'Start Free Trial'}]], 'resize_keyboard': True}})
                c.execute("INSERT OR REPLACE INTO state VALUES ('offset', ?)", (update['update_id'] + 1,))
                c.commit()
        except Exception:
            # Never log API URLs or credentials. Retry conservatively.
            print('Polling or delivery failed; retrying.', flush=True)
            time.sleep(5)

if __name__ == '__main__':
    main()
