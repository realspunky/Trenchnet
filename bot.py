"""TrenchNet command bot. Public alerts and payment acceptance are disabled."""
import json
import os
import sqlite3
import time
import urllib.request
from alert_preferences import setup as alert_pref_setup, keyboard as alert_keyboard, summary as alert_summary, toggle as alert_toggle, set_all as alert_set_all

DB = os.environ.get('DATABASE_PATH', 'trenchnet.sqlite3')

def database():
    c = sqlite3.connect(DB, timeout=30)
    c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, threshold INTEGER NOT NULL DEFAULT 80 CHECK(threshold BETWEEN 80 AND 95))')
    c.execute('CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value INTEGER)')
    c.commit()
    alert_pref_setup(c)
    return c

def reply(c, user_id, text):
    c.execute('INSERT OR IGNORE INTO users(id) VALUES (?)',(user_id,));c.commit()
    parts=text.split()
    cmd=parts[0].split('@')[0] if parts else ''
    if cmd in {'/start','/help'}:
        return ('Welcome to TrenchNet V2.\n/alerts — select launchpads\n'
                '/delete_me — delete your settings')
    if cmd=='/myid':return f'Your Telegram user ID: {user_id}'
    if cmd=='/alerts':
        return alert_summary(c,user_id)+'\nUse the buttons to turn each launchpad on or off.'
    if cmd=='/status':
        if str(user_id)!=os.environ.get('ADMIN_CHAT_ID'):return 'Use /help to see available commands.'
        from v2_status import build
        return build(c)
    if cmd=='/delete_me':
        with c:
            c.execute('DELETE FROM user_launchpad_preferences WHERE user_id=?',(user_id,))
            c.execute('DELETE FROM users WHERE id=?',(user_id,))
        return 'Your saved TrenchNet settings have been deleted.'
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


def _public_commands():
    return [{'command':'start','description':'Open TrenchNet V2'},
            {'command':'alerts','description':'Choose launchpad alerts'},
            {'command':'help','description':'Show commands'},
            {'command':'delete_me','description':'Remove saved settings'}]

def sync_command_menu(token):
    """Replace Telegram's cached slash-command menu."""
    commands = _public_commands()
    api(token, 'setMyCommands', {'commands': commands, 'scope': {'type':'default'}})
    # Clear any older per-chat command scope. A chat-specific scope overrides the
    # default menu, which previously caused /status to reappear for the admin.
    admin = os.environ.get('ADMIN_CHAT_ID')
    if admin:
        try:
            api(token, 'deleteMyCommands', {
                'scope': {'type':'chat','chat_id': int(admin)}
            })
        except (ValueError, TypeError):
            pass

def main():
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if not token:
        raise SystemExit('Set TELEGRAM_BOT_TOKEN securely in the server environment.')
    c = database()
    sync_command_menu(token)
    while True:
        try:
            row = c.execute("SELECT value FROM state WHERE key='offset'").fetchone()
            offset = row[0] if row else 0
            updates = api(token, 'getUpdates', {'offset': offset, 'timeout': 25, 'allowed_updates': ['message','callback_query']})
            for update in updates:
                msg = update.get('message', {})
                if msg.get('chat', {}).get('type') == 'private' and 'text' in msg:
                    uid=msg['from']['id']; result=reply(c,uid,msg['text'])
                    markup = alert_keyboard(c,uid) if msg['text'].split()[0].split('@')[0]=='/alerts' else {'remove_keyboard': True}
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
