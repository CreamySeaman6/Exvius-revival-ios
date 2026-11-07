"""Supply the original native exchange screens with recovered shop stock."""
from collections import defaultdict
from functools import lru_cache
import json
import os
from pathlib import Path
import time

from data_paths import TEXT_DIR
from exvius_actions_shops import (_action, _feature, _grant, _int, _node, _pay,
                                  _reply, _require, _rewards, _rows, _store)
from exvius_rewards import parse
from ffbe_state import State

START = '2020-01-01 00:00:00'
END = '2099-12-31 23:59:59'
# Exchange shops tied to events (content/event_shops.json): detail id -> (event areas, cost kind, currency).
EVENT_SHOPS = {}
# NV Unit Select ticket exchanges (detail id -> (kind, ticket item id)), hidden while the player holds none.
TICKET_SHOPS = {}


def _deal_ticket_ids() -> list:
    """The NV Unit Select tickets the deal summons pay (gacha_deals.json), whose exchanges the client ships in
    F_MEDAL_EXCHANGE_MST (Unit Select 10+1 NV Guaranteed, 7th Anniversary Select Step-Up; 2026-11-07)."""
    try:
        doc = json.loads(Path(__file__).with_name('gacha_deals.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    found = {str(t) for banner in doc.get('banners', []) for t in banner.get('unit_select_tickets') or []}
    return sorted(found, key=int)


def catalogue():
    """The shop catalogue; with the historical replay on, units not yet released are left out."""
    try:
        import replay
        cutoff = replay.pool_cutoff()
    except Exception:  # noqa: BLE001 -- no replay limit
        cutoff = None
    return _catalogue(cutoff.isoformat() if cutoff else None)


@lru_cache(maxsize=4)
def _catalogue(cutoff=None):
    # Fragment exchanges retain their original currency, quantity and limits.
    names = {}
    path = Path(TEXT_DIR) / 'F_TEXT_ITEM_NAME.ndjson'
    for line in path.read_text(encoding='utf-8').splitlines():
        row = json.loads(line)
        names[row['key'].rsplit('_', 1)[-1]] = row['v'][0]
    currencies = defaultdict(list)
    for row in _rows('F_MEDAL_EXCHANGE_MST'):
        if not str(row.get('7iJpH5zZ', '')).startswith('20:250'):
            continue
        rewards = parse(row.get('7iJpH5zZ'))
        if len(rewards) == 1 and rewards[0]['kind'] == 20 and str(rewards[0]['id']).startswith('250'):
            currencies[str(row['ak2dhKm3'])].append((row, rewards[0]))
    details, products, offers = [], [], {}

    def detail(did, title, kind, currency, category, banner=0):
        details.append({'3X1gLufw': str(did), 'X1IuZnj2': '0', 'JV8AIH3n': str(category),
                        'Z0EN6jSh': str(len(details) + 1), 'fSxqkF10': str(banner), 'uYcL8IQ1': '-1',
                        '6uvHX2JG': title, 'VjJQ51uG': START, 'm8ivD4NX': END,
                        '0GgK6ytT': str(kind) + ':' + str(currency)})

    # Products left out of the shops that are priced in Lapis (EXVIUS_LAPIS_SHOP_EXCLUDE, `kind:id` comma list).
    # Default: King Metal Minituar (10:900020401). Those shops' original coins have no source here, so they
    # sell for Lapis 1:1, which made the best EXP material cost 3 Lapis, unlimited (audit 2026-11-05).
    excluded = {entry.strip() for entry in os.environ.get('EXVIUS_LAPIS_SHOP_EXCLUDE', '10:900020401').split(',')
                if entry.strip()}

    def product(pid, did, reward, price, limit, currency, monthly=False):
        if currency[0] == 50 and ':'.join(str(reward).split(':')[:2]) in excluded:
            return
        if cutoff:
            import replay
            from datetime import date
            if any(r['kind'] == 10 and not replay.released_by(r['id'], date.fromisoformat(cutoff))
                   for r in parse(reward)):
                return
        row = {'jPV7Xc4N': str(pid), '3X1gLufw': str(did), 'P4puB2ch': reward,
               'e4mG8jTc': str(price), 'uYcL8IQ1': str(-1 if int(limit) == 2147483647 else limit),
               'Z0EN6jSh': str(len(products) + 1),
               '6uvHX2JG': '', 'VjJQ51uG': START, 'm8ivD4NX': END, 'fbcj5Aq9': '', 'JasF1S3u': ''}
        products.append(row)
        offers[str(pid)] = {'detail': str(did), 'rewards': parse(reward), 'cost': currency,
                            'price': int(price), 'limit': int(limit), 'monthly': monthly}

    for index, (currency, stock) in enumerate(sorted(currencies.items(), key=lambda pair: int(pair[0]))):
        did = 850000000 + index
        detail(did, names.get(currency, 'Fragment Exchange'), 20, currency, 5)
        for row, _reward in stock:
            limit = int(row['x0NDnEC9']) if row['kR4n5DxP'] == '1' else 2147483647
            product(900000000 + int(row['S21FT3L8']), did, row['7iJpH5zZ'], row['Qy5EvcK1'],
                    limit, (20, currency))

    # NV Unit Select exchanges: trade the ticket a deal summon paid for one NV of the listed ones (the client's
    # own rows). Units not yet released in the replay are left out by product() like everywhere else.
    unit_rows = defaultdict(list)
    tickets = set(_deal_ticket_ids())
    for row in _rows('F_MEDAL_EXCHANGE_MST'):
        if str(row.get('ak2dhKm3')) in tickets and str(row.get('7iJpH5zZ', '')).startswith('10:'):
            unit_rows[str(row['ak2dhKm3'])].append(row)
    for index, currency in enumerate(sorted(unit_rows, key=int)):
        did = 850003000 + index
        detail(did, names.get(currency, 'NV Unit Select').strip(), 20, currency, 5)
        for row in unit_rows[currency]:
            limit = int(row['x0NDnEC9']) if row['kR4n5DxP'] == '1' else 2147483647
            product(900000000 + int(row['S21FT3L8']), did, row['7iJpH5zZ'], row['Qy5EvcK1'],
                    limit, (20, currency))
        TICKET_SHOPS[str(did)] = (20, currency)

    # Original monthly VIP stock and prices, recorded on the preservation wiki.
    # https://exvius.fandom.com/wiki/VIP_Coin#Exchange_Shop
    did = 850001000
    detail(did, 'VIP Shop', 50, 1, 6, 10)
    vip = [
        ('23:110260:10', 10000, 1), ('23:110260:1', 1000, 1),
        ('23:80:1', 1750, 1), ('23:50:2', 200, 2),
        ('23:110180:1', 1400, 2), ('23:110160:3', 200, 5),
        ('20:900000001:1', 2500, 1),
        ('10:904000105:1:100:1:500:0:0:100000050', 200, 8),
        ('20:293000200:1', 200, 3), ('20:293000100:1', 1000, 2),
        ('10:900010501:10', 60, 20), ('10:900020401:10:100:60', 70, 20),
        ('27:900020101:1', 700, 10), ('20:1209001274:30', 200, 10),
    ]
    for index, (reward, price, limit) in enumerate(vip):
        product(940000000 + index, did, reward, price, limit, (50, '1'), True)
    recovered = json.loads(Path(__file__).with_name('content').joinpath('permanent_shops.json').read_text())
    for index, shop in enumerate(recovered['shops']):
        did = 850001001 + index
        kind, currency = shop['currency']
        category = shop.get('category', 6)
        if category == 6:
            kind, currency = 50, '1'
        banner = 60 if shop['name'] == 'EX Coin Shop' else 0
        detail(did, shop['name'], kind, currency, category, banner)
        for position, row in enumerate(shop['products']):
            product(940001000 + index * 1000 + position, did, row['reward'], row['price'],
                    row['limit'], (kind, currency), shop['reset_months'])
    # Event exchanges made here for events whose own key-spending stages were never shipped (e.g. the
    # Skeleton Key Exchange for Return to the Halloween Castle). Shown only while the event is open, or
    # while the player still holds the currency (entry() below).
    path = Path(__file__).with_name('content').joinpath('event_shops.json')
    events = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'shops': []}
    for index, shop in enumerate(events['shops']):
        did = 850002000 + index
        kind, currency = shop['currency']
        detail(did, shop['name'], kind, currency, shop.get('category', 4))
        for position, row in enumerate(shop['products']):
            product(950000000 + index * 1000 + position, did, row['reward'], row['price'],
                    row['limit'], (kind, str(currency)))
        EVENT_SHOPS[str(did)] = ([str(area) for area in shop.get('event_areas', [])], kind, str(currency))
    return details, products, offers


def hidden_details():
    """Event exchanges to leave out now: their event is not in this week's Vortex and the player holds
    none of their currency."""
    hidden = set()
    for did, (kind, currency) in TICKET_SHOPS.items():
        if not (State.player.item_count(kind, currency) if State.player is not None else 0):
            hidden.add(did)
    if not EVENT_SHOPS:
        return hidden
    try:
        import event_archive
        open_areas = {str(row['area']) for row in event_archive.weekly_events()}
    except Exception:  # noqa: BLE001 -- without the rotation, every event exchange shows
        return hidden
    for did, (areas, kind, currency) in EVENT_SHOPS.items():
        if open_areas.intersection(areas):
            continue
        held = State.player.item_count(kind, currency) if State.player is not None else 0
        if not held:
            hidden.add(did)
    return hidden


def receipt_key(pid, offer):
    if not offer['monthly']:
        return pid
    months = int(offer['monthly'])
    now = time.localtime()
    period = (now.tm_year * 12 + now.tm_mon - 1) // months
    return pid + '/' + str(period)


@lru_cache(maxsize=1)
def labels():
    names = {}
    for kind, table in [(20, 'ITEM'), (23, 'IMPORTANT_ITEM'), (10, 'UNITS'), (27, 'VISION_CARD'),
                        (21, 'ITEM_EQUIP'), (22, 'MATERIA'), (60, 'RECIPE_BOOK')]:
        path = Path(TEXT_DIR) / ('F_TEXT_' + table + '_NAME.ndjson')
        for line in path.read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            names[kind, row['key'].rsplit('_', 1)[-1]] = row['v'][0].strip()
    result = {}
    for pid, offer in catalogue()[2].items():
        texts = []
        for row in offer['rewards']:
            name = names[row['kind'], str(row['id'])]
            if row.get('affinity_points', [''])[0]:
                name += ' (ALL ' + str(int(row['affinity_points'][0]) // 10) + '%)'
            if row['count'] > 1:
                name += ' x' + str(row['count'])
            texts.append(name)
        title = ', '.join(texts)
        result[pid] = {'name': title, 'description': 'Exchange for ' + title + '.'}
    return result


def entry(spec, req):
    details, products, offers = catalogue()
    hidden = hidden_details()
    out = _reply(spec)
    out['F2rNo6qf'] = [dict(row) for row in details if row['3X1gLufw'] not in hidden]
    out['TPrh6Ay3'] = [dict(row) for row in products if row['3X1gLufw'] not in hidden]
    counts = _feature('shop_catalogue').get('counts', {})
    out['qS62ewjH'] = [{'jPV7Xc4N': pid, '3X1gLufw': offer['detail'],
                        'Q8GLK1pz': str(counts.get(receipt_key(pid, offer), 0))}
                       for pid, offer in offers.items() if offer['detail'] not in hidden]
    return out


@_action
def purchase(spec, req):
    node = _node(req, '4mrD6JuA') or {}
    pid = str(node.get('jPV7Xc4N', ''))
    offer = catalogue()[2].get(pid)
    _require(offer is not None, 'unknown exchange product')
    quantity = _int(node.get('Qy5EvcK1'), 1)
    counts = dict(_feature('shop_catalogue').get('counts', {}))
    key = receipt_key(pid, offer)
    bought = int(counts.get(key, 0))
    _require(bought + quantity <= offer['limit'], 'exchange stock exhausted')
    rewards = [dict(row, count=row['count'] * quantity) for row in offer['rewards']]
    _rewards(rewards)
    kind, currency = offer['cost']
    amount = offer['price'] * quantity
    if kind == 50:
        _require(State.player.spend_lapis(amount), 'not enough Lapis')
    else:
        _pay([{'kind': kind, 'id': currency, 'count': amount}])
    _grant(rewards)
    counts[key] = bought + quantity
    _store('shop_catalogue', {'counts': counts})
    out = _reply(spec)
    out['4owH1uT2'] = [{'jPV7Xc4N': pid, '3X1gLufw': offer['detail'], 'Q8GLK1pz': str(counts[key])}]
    return out
