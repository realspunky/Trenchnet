"""Telegram delivery transport for TrenchNet V2."""
import json,re,time
def alert_payload(recipient, text):
    payload = {'chat_id': recipient, 'text': text, 'disable_web_page_preview': True}
    match = re.search(r'^(?:📋 )?Contract: (0x[0-9a-fA-F]{40}|[1-9A-HJ-NP-Za-km-z]{32,44})$', text, re.MULTILINE)
    if match:
        address = match.group(1)
        # Telegram entity offsets count UTF-16 units, including preceding emojis.
        offset = len(text[:match.start(1)].encode('utf-16-le')) // 2
        payload['entities'] = [{'type': 'code', 'offset': offset, 'length': len(address)}]
        buttons=[{'text': '📋 Copy contract', 'copy_text': {'text': address}}]
        xm=re.search(r'^𝕏 X: (https?://\S+)$', text, re.MULTILINE)
        wm=re.search(r'^🌐 Website: (https?://\S+)$', text, re.MULTILINE)
        if xm: buttons.append({'text':'𝕏 X','url':xm.group(1)})
        if wm: buttons.append({'text':'🌐 Website','url':wm.group(1)})
        payload['reply_markup'] = {'inline_keyboard': [buttons]}
    return payload

def deliver(c,token,send,table="pilot_outbox"):
    if table not in {"pilot_outbox", "stonk_outbox", "pons_outbox", "ember_outbox", "pumpfun_outbox", "global_outbox"}:raise ValueError("Invalid delivery table")
    from urllib.error import HTTPError
    with c:
        c.execute(f"UPDATE {table} SET state='expired' WHERE state='pending' AND expires<=?",(int(time.time()),))
    row=c.execute(f"SELECT id,recipient,body,attempts FROM {table} WHERE state='pending' AND next_attempt<=? ORDER BY id LIMIT 1",(int(time.time()),)).fetchone()
    if not row:return False
    ident,recipient,text,attempts=row
    with c:c.execute(f"UPDATE {table} SET state='sending' WHERE id=?",(ident,))
    try:
        result=send(token,'sendMessage',alert_payload(recipient,text))
        with c:c.execute(f"UPDATE {table} SET state='sent',message_id=? WHERE id=?",(result['message_id'],ident))
    except HTTPError as e:
        # Telegram's explicit rate rejection can be retried. Others require review.
        retry=60
        if e.code==429:
            try:retry=max(1,int(json.load(e).get('parameters',{}).get('retry_after',60)))
            except Exception:pass
        state='pending' if e.code==429 and attempts<5 else 'review'
        with c:c.execute(f'UPDATE {table} SET state=?,attempts=?,next_attempt=? WHERE id=?',
                         (state,attempts+1,int(time.time())+retry,ident))
    except Exception:
        with c:c.execute(f"UPDATE {table} SET state='uncertain' WHERE id=?",(ident,))
        print('Private alert delivery uncertain; retained for review, not resent.',flush=True)
    return True

