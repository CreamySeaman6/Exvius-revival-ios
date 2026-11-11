"""The original five-star unit/prism selector and its shipped ticket prices."""
import copy
from datetime import datetime

from exvius_actions import _node, _mst, _refresh
from ffbe_state import State, _note


# Limited and collaboration 5★ units in the 5★ Select list (operator, 2026-11-10: "Limited and collab I'm
# okay having in, the other stuff no ... nor Japan"). The client's F_GACHA_SELECT_UNIT_MST lists 234 regular
# 5★ units; `extra_unit_rows` adds every base-5★ unit gacha_archive.limited_unit_ids flags that Global had
# (content/unit_release_global.json `units`, page not a /JP one), at the same price (10) and window. ios_tables
# serves the table with these rows; `_execute` accepts them. Story/reward/Star Quartz/raid units and Japan-only
# units stay out. EXVIUS_SELECT_LIMITED=0 serves the shipped list.
SELECT_START, SELECT_END = '2017-01-01 00:00:00', '2030-12-31 23:59:59'
_EXTRA = None


def limited_enabled():
    import os
    return str(os.environ.get('EXVIUS_SELECT_LIMITED', '1')).strip().lower() not in ('0', 'off', 'false', 'no')


def extra_unit_rows():
    """Rows (`3HriTp6B`, `e4mG8jTc`, `VjJQ51uG`, `m8ivD4NX`) added to the 5★ Select list."""
    global _EXTRA
    if not limited_enabled():
        return []
    if _EXTRA is None:
        import json
        import os
        import gacha_archive
        from player_state import unit_roots_by_rarity
        shipped = set(_mst('F_GACHA_SELECT_UNIT_MST.ndjson', '3HriTp6B'))
        try:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'content', 'unit_release_global.json')
            with open(path, encoding='utf-8') as fh:
                globl = json.load(fh).get('units') or {}
        except (OSError, ValueError):
            globl = {}
        limited = {str(u) for u in gacha_archive.limited_unit_ids()}
        import summon_exclusions      # story/reward/Star Quartz/raid units: never in the list
        story = {str(u) for u in (summon_exclusions._doc().get('excluded') or {})}
        roots = [str(u) for u in unit_roots_by_rarity().get('5', []) if not str(u).startswith('9')]
        _EXTRA = [{'3HriTp6B': u, 'e4mG8jTc': '10', 'VjJQ51uG': SELECT_START, 'm8ivD4NX': SELECT_END}
                  for u in sorted(roots, key=int)
                  if u in limited and u not in story and u not in shipped and u in globl
                  and not str(globl[u].get('page') or '').endswith('/JP')]
    return list(_EXTRA)


def entry(spec, req):
    # Unit and prism choices are in the original cached F_GACHA_SELECT_* tables.
    from exvius_shop_catalogue import entry as shop_entry
    return shop_entry(spec, req)


def _execute(spec, req, prism=False):
    from ffbe_gacha import all_banners, _award_str
    from player_state import effect_pattern_for, unit_mst
    player = State.player
    tag = 'tCq8mcNo' if prism else 'u9jY6hQJ'
    def decline():
        out = _refresh(spec)
        out[tag] = [{'UJz5QED2': '', 'oY0vAuE9': '0', 'zoU5J3Kq': '1',
                     'X1IuZnj2': '0', 'nqzG3b2v': '0', 'zJ1A6HXm': '0', '2RtVPS3b': '0'}]
        return out
    if player is None or player.mode == 'frozen':
        return decline()
    node = _node(req, tag) or {}
    banner = next((b for b in all_banners() if str(b['id']) == str(node.get('X1IuZnj2')) and
                   b.get('selection')), None)
    if banner is None or str(node.get('nqzG3b2v')) != str(banner['detail_id']):
        _note('Select summon: unknown banner or detail')
        return decline()
    iid = str(node.get('tL6G9egd' if prism else '3HriTp6B', ''))
    table = _mst('F_GACHA_SELECT_PRISM_MST.ndjson' if prism else 'F_GACHA_SELECT_UNIT_MST.ndjson',
                 'tL6G9egd' if prism else '3HriTp6B')
    if not prism and iid not in table:
        table = dict(table, **{r['3HriTp6B']: r for r in extra_unit_rows()})
    row = table.get(iid)
    today = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    first, last = ('Tx6MGkJ1', '2CL6pZmE') if prism else ('VjJQ51uG', 'm8ivD4NX')
    if row is None or not row[first] <= today <= row[last]:
        _note('Select summon: selected reward is not in the original available master')
        return decline()
    cost = int(row['e4mG8jTc'])
    reward = {'kind': 20 if prism else 10, 'id': int(iid), 'count': 1}
    if cost < 1 or not player._can_credit(reward):
        return decline()
    before, dirty = copy.deepcopy(player.data), player.dirty
    if not player.spend_item(23, 260, cost):
        _note('Select summon: insufficient five-star select tickets')
        return decline()
    try:
        if prism:
            if player._grant_items([reward]) != [reward]:
                raise ValueError('Selected prism could not be granted')
            result = {'UJz5QED2': '20:' + iid + ':1'}
        else:
            unit = player.grant_unit(iid, granted_rarity=5)
            award = {'unit_id': iid, 'instance_id': unit['instance_id'], 'level': unit['level']}
            result = {'X1IuZnj2': str(banner['id']), 'nqzG3b2v': str(banner['detail_id']),
                      'UJz5QED2': _award_str(award), 'zJ1A6HXm': '1', '2RtVPS3b': '0',
                      'zoU5J3Kq': str(effect_pattern_for(int(unit_mst(iid)['9fW0TePj']), banner['id'])),
                      'oY0vAuE9': '1'}
        out = _refresh(spec)
        out[tag] = [result]
        return out
    except Exception:
        player.data, player.dirty = before, dirty
        raise


def select_unit(spec, req):
    return _execute(spec, req)


def select_prism(spec, req):
    return _execute(spec, req, prism=True)


from exvius_shop_catalogue import purchase as shop_purchase
HANDLERS = {'6nTcSp4R': entry, 'xio14KrL': select_unit, 'bgast6dR': select_prism,
            'W58vo4Hp': shop_purchase}
