"""Shared launch-noise filtration for TrenchNet.

Contract addresses remain unique identities. Names/symbols are normalized only to
cluster repeated launches; they are never treated as proof that two tokens are the
same asset.
"""
import re
import time
import unicodedata


def normalize_label(value):
    value = unicodedata.normalize('NFKC', str(value or '')).casefold()
    return re.sub(r'[^a-z0-9]+', '', value)


def setup(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS launch_observations(
      chain TEXT NOT NULL, launchpad TEXT NOT NULL, address TEXT NOT NULL,
      creator TEXT, name_key TEXT NOT NULL, symbol_key TEXT NOT NULL,
      observed INTEGER NOT NULL,
      PRIMARY KEY(chain,address));
    CREATE INDEX IF NOT EXISTS launch_name_window ON launch_observations(chain,name_key,symbol_key,observed);
    CREATE INDEX IF NOT EXISTS launch_creator_window ON launch_observations(chain,creator,observed);
    CREATE TABLE IF NOT EXISTS launch_filter_stats(
      reason TEXT PRIMARY KEY, count INTEGER NOT NULL DEFAULT 0);
    ''')
    c.commit()


def assess(c, *, chain, launchpad, address, creator, name, symbol, now=None,
           duplicate_window=900, creator_window=1800, creator_limit=3):
    """Record a launch and return the alert decision.

    First same-name/symbol contract in a rolling window is allowed. Later contracts
    are suppressed and counted as a duplicate cluster. A creator producing many
    distinct contracts in a short window is flagged; after creator_limit launches,
    additional alerts are suppressed. Thresholds are configurable by callers/env.
    """
    setup(c)
    now = int(time.time() if now is None else now)
    name_key, symbol_key = normalize_label(name), normalize_label(symbol)
    creator_key = str(creator or '').lower()
    address_key = str(address).lower()
    cutoff = now - int(duplicate_window)
    creator_cutoff = now - int(creator_window)

    duplicate = c.execute('''SELECT COUNT(*),COUNT(DISTINCT creator) FROM launch_observations
        WHERE chain=? AND name_key=? AND symbol_key=? AND observed>=? AND address<>?''',
        (chain,name_key,symbol_key,cutoff,address_key)).fetchone()
    creator_count = 0
    if creator_key:
        creator_count = c.execute('''SELECT COUNT(DISTINCT address) FROM launch_observations
            WHERE chain=? AND creator=? AND observed>=? AND address<>?''',
            (chain,creator_key,creator_cutoff,address_key)).fetchone()[0]

    with c:
        c.execute('''INSERT OR IGNORE INTO launch_observations
            (chain,launchpad,address,creator,name_key,symbol_key,observed) VALUES(?,?,?,?,?,?,?)''',
            (chain,launchpad,address_key,creator_key,name_key,symbol_key,now))

    dup_count, unique_creators = duplicate
    if dup_count:
        reason='duplicate_name_cluster'
        with c:c.execute('''INSERT INTO launch_filter_stats(reason,count) VALUES(?,1)
            ON CONFLICT(reason) DO UPDATE SET count=count+1''',(reason,))
        return {'allow':False,'reason':reason,'duplicates':dup_count+1,
                'unique_creators':unique_creators + (0 if creator_key and unique_creators else 1),
                'creator_launches':creator_count+1}
    if creator_key and creator_count >= int(creator_limit):
        reason='creator_multi_launch'
        with c:c.execute('''INSERT INTO launch_filter_stats(reason,count) VALUES(?,1)
            ON CONFLICT(reason) DO UPDATE SET count=count+1''',(reason,))
        return {'allow':False,'reason':reason,'duplicates':1,'unique_creators':1,
                'creator_launches':creator_count+1}
    return {'allow':True,'reason':'first_qualifying','duplicates':1,'unique_creators':1,
            'creator_launches':creator_count+1}
