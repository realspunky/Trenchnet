"""TrenchNet command bot. Public alerts and payment acceptance are disabled."""
import json
import os
import sqlite3
import time
import urllib.request
from access import setup, start_trial, state
from alert_preferences import setup as alert_pref_setup, keyboard as alert_keyboard, summary as alert_summary, toggle as alert_toggle, set_all as alert_set_all

DB = os.environ.get('DATABASE_PATH', 'trenchnet.sqlite3')

def database():
    c = sqlite3.connect(DB, timeout=30)
    c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, threshold INTEGER NOT NULL DEFAULT 80 CHECK(threshold BETWEEN 80 AND 95))')
    c.execute('CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value INTEGER)')
    c.commit()
    setup(c)
    alert_pref_setup(c)
    return c

def qualifies(token):
    return (token.get('verified') is True
            and token.get('launchpad') in {'pons', 'flap', 'stonk'}
            and token.get('chain') in {'solana', 'bnb', 'robinhood'}
            and token.get('total_tax_bps') in {100, 200, 300}
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
                '/alerts — choose launchpads for alerts\n'
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
    if cmd == '/alerts':
        return alert_summary(c,user_id) + '\nUse the buttons below to turn each launchpad on or off.'
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
            try:
                stonk_health=c.execute('SELECT updated,status FROM stonk_health WHERE id=1').fetchone()
            except sqlite3.OperationalError:
                stonk_health=None
            if stonk_health:
                age=max(0,int(time.time())-stonk_health[0])
                monitoring += f'\nStonk: {stonk_health[1]}\nStonk update: {age}s ago'
                if age>300:monitoring += ' (stale; check logs)'
                for label,table,column in [('Stonk tokens','stonk_tokens','status'),('Stonk deliveries','stonk_outbox','state')]:
                    rows=c.execute(f'SELECT {column},COUNT(*) FROM {table} GROUP BY {column}').fetchall()
                    monitoring += '\n'+label+': '+(', '.join(f'{k}={v}' for k,v in rows) or 'none yet')
            elif os.environ.get('STONK_ENABLED')=='true':
                monitoring += '\nStonk scanner has not reported yet'
            try:
                pons_health=c.execute('SELECT updated,status FROM pons_health WHERE id=1').fetchone()
            except sqlite3.OperationalError:
                pons_health=None
            if pons_health:
                age=max(0,int(time.time())-pons_health[0])
                monitoring += f'\nPONS: {pons_health[1]}\nPONS update: {age}s ago'
                if age>180:monitoring += ' (stale; check logs)'
                for label,table,column in [('PONS tokens','pons_tokens','status'),('PONS deliveries','pons_outbox','state')]:
                    rows=c.execute(f'SELECT {column},COUNT(*) FROM {table} GROUP BY {column}').fetchall()
                    monitoring += '\n'+label+': '+(', '.join(f'{k}={v}' for k,v in rows) or 'none yet')
            elif os.environ.get('PONS_ENABLED')=='true':
                monitoring += '\nPONS scanner has not reported yet'
            for label,enabled,health_table,token_table,outbox_table in [
                ('EmberCurve','EMBER_ENABLED','ember_health','ember_tokens','ember_outbox'),
                ('Pump.fun','PUMPFUN_ENABLED','pumpfun_health','pumpfun_tokens','pumpfun_outbox')]:
                try:
                    h=c.execute(f'SELECT updated,status FROM {health_table} WHERE id=1').fetchone()
                except sqlite3.OperationalError:
                    h=None
                if h:
                    age=max(0,int(time.time())-h[0])
                    monitoring += f'\n{label}: {h[1]}\n{label} update: {age}s ago'
                    if age>180: monitoring += ' (stale; check logs)'
                    try:
                        total=c.execute(f'SELECT COUNT(*) FROM {token_table}').fetchone()[0]
                        monitoring += f'\n{label} tokens: {total}'
                        states=c.execute(f'SELECT state,COUNT(*) FROM {outbox_table} GROUP BY state').fetchall()
                        monitoring += f'\n{label} deliveries: '+(', '.join(f'{k}={v}' for k,v in states) or 'none yet')
                    except sqlite3.OperationalError: pass
                elif os.environ.get(enabled)=='true':
                    monitoring += f'\n{label} scanner has not reported yet'

        return f'Bonding threshold: {threshold}%\nAccess: {kind}\nExpiry: {expiry_text}\n{monitoring}'
    if cmd == '/plans':
        return ('Planned prices: $5 monthly / $60 for 12 months / $100 lifetime. '
                'Free trial: five days, up to one qualifying alert per day; no automatic charge. Checkout is disabled. Telegram requires Stars for digital subscriptions sold inside bots. '
                'Payment design and Stars pricing are not finalized. Do not send funds.')
    if cmd == '/email':
        return 'Optional verified email alerts are planned. Email collection is not enabled yet.'
    if cmd == '/delete_me':
        alert_pref_setup(c)
        c.execute('DELETE FROM users WHERE id=?', (user_id,))
        c.execute('DELETE FROM user_launchpad_preferences WHERE user_id=?', (user_id,))
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
            updates = api(token, 'getUpdates', {'offset': offset, 'timeout': 25, 'allowed_updates': ['message','callback_query']})
            for update in updates:
                msg = update.get('message', {})
                if msg.get('chat', {}).get('type') == 'private' and 'text' in msg:
                    uid=msg['from']['id']; result=reply(c,uid,msg['text'])
                    markup = alert_keyboard(c,uid) if msg['text'].split()[0].split('@')[0]=='/alerts' else {'keyboard': [[{'text': 'Start Free Trial'}]], 'resize_keyboard': True}
                    api(token, 'sendMessage', {'chat_id': msg['chat']['id'], 'text': result, 'reply_markup': markup})
                cq=update.get('callback_query')
                if cq and cq.get('data','').startswith('alerts:'):
                    uid=cq['from']['id']; data=cq['data']; parts=data.split(':')
                    if parts[1]=='toggle': alert_toggle(c,uid,parts[2])
                    elif parts[1]=='all': alert_set_all(c,uid,parts[2]=='on')
                    api(token,'answerCallbackQuery',{'callback_query_id':cq['id']})
                    if parts[1]=='done':
                        api(token,'editMessageText',{'chat_id':cq['message']['chat']['id'],'message_id':cq['message']['message_id'],'text':alert_summary(c,uid)})
                    else:
                        api(token,'editMessageText',{'chat_id':cq['message']['chat']['id'],'message_id':cq['message']['message_id'],'text':alert_summary(c,uid)+'\nUse the buttons below to turn each launchpad on or off.','reply_markup':alert_keyboard(c,uid)})
                c.execute("INSERT OR REPLACE INTO state VALUES ('offset', ?)", (update['update_id'] + 1,))
                c.commit()
        except Exception:
            # Never log API URLs or credentials. Retry conservatively.
            print('Polling or delivery failed; retrying.', flush=True)
            time.sleep(5)

if __name__ == '__main__':
    main()
