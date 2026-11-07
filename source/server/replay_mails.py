"""Mails Global sent to every player on a given day, delivered when the historical replay reaches that day.

The list is content/replay_mails.json: each entry has an `id`, the Global `date` (YYYY-MM-DD), a `title`, a
`message` and either fixed `items` ([kind, id, count], ...) or `by_days` for gifts that depended on how long
the player had been playing (the Player Appreciation tickets: [[up_to_days, count], ..., [null, count]] of one
`item`). Days played are counted in history: from the replay's start (EXVIUS_REPLAY_START) to the mail's date,
as if the player had logged in every day of the history they have played through.

Each mail goes out once per save (`data.replay_mails`), on the same replies as the weekly summon gift.
Off with EXVIUS_REPLAY_MAILS=0, or with the replay off (2026-11-07).
"""
import json
import os
from datetime import date

_HERE = os.path.dirname(os.path.abspath(__file__))
MAILS_FILE = os.path.join(_HERE, 'content', 'replay_mails.json')
_MAILS: list | None = None


def enabled() -> bool:
    return os.environ.get('EXVIUS_REPLAY_MAILS', '1') == '1'


def mails() -> list:
    global _MAILS
    if _MAILS is None:
        try:
            with open(MAILS_FILE, encoding='utf-8') as fh:
                _MAILS = json.load(fh).get('mails', [])
        except (OSError, ValueError):
            _MAILS = []
    return _MAILS


def items_for(mail: dict, start: date) -> list[tuple[int, int, int]]:
    """The mail's attachments; a `by_days` mail counts the days from `start` to its date."""
    if mail.get('items'):
        return [(int(k), int(i), int(c)) for k, i, c in mail['items']]
    kind, item_id = mail['item']
    days = (date.fromisoformat(mail['date']) - start).days + 1
    for limit, count in mail['by_days']:
        if limit is None or days <= int(limit):
            return [(int(kind), int(item_id), int(count))]
    return []


def due(reached: date) -> list:
    """Mails whose Global date falls before `reached` (the end of this week's slice of history)."""
    return [m for m in mails() if date.fromisoformat(m['date']) < reached]


def deliver(spec, reply_id):
    """Mail every replay mail whose date history has reached and this save hasn't had yet."""
    from ffbe_state import State
    from ffbe_config import ANNIVERSARY_TICKET_CARRIER
    if (not enabled() or reply_id not in ANNIVERSARY_TICKET_CARRIER.split(",") or State.player is None
            or not isinstance(spec, dict) or State.player.mode == "frozen"):
        return spec
    try:
        import replay
        if not replay.enabled():
            return spec
        win = replay.window()
        start = replay.start_date()
    except Exception:  # noqa: BLE001 -- no replay window: nothing is due
        return spec
    sent = State.player.data.setdefault('replay_mails', [])
    for mail in due(win['to']):
        if mail['id'] in sent:
            continue
        items = items_for(mail, start)
        if not items:
            continue
        State.player.deliver_mail(mail['title'], items, mail_id=str(mail['id']), message=mail.get('message', ''),
                                  icon_type=2, attach_type=1)
        sent.append(mail['id'])
        State.player.dirty = True
        print(f"replay mail: {mail['id']} ({mail['date']}) mailed {items}", flush=True)
    return spec
