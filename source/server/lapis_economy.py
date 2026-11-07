"""Earned-Lapis tuning: the game's Lapis income was balanced around buying Lapis, which this server can't.

Three knobs, all for Lapis you EARN by playing (Shop purchases are never touched):

  EXVIUS_LAPIS_MULTIPLIER (default 5)     every earned Lapis amount is multiplied: mission challenges, event
                                          repeats, rank-ups, login and catch-up mails, quests, raids, arena...
  EXVIUS_DAILY_QUEST_LAPIS (default 150)  every daily quest pays this much Lapis (the original server's
                                          daily rewards were never preserved; the ones here were authored)
  EXVIUS_DAILY_ALL_BONUS (default 200)    extra Lapis for finishing all of a day's daily quests
  EXVIUS_WEEKLY_GIFT (default "23:50:10,23:70:1")
                                          mailed once per summon-rotation week: 10 Rare Summon Tickets and a
                                          Guaranteed Ticket (4★/5★/NV), a 10+1's worth to use with any banner's
                                          Ticket Summon button. "" turns it off.

Set the multiplier to 1, the daily values to 0 and the gift to "" to get the stock economy back. The multiplier
and daily amounts are applied before the daily bonus is multiplied, so with the defaults a full day of
dailies pays (3 x 150 + 200) x 5 = 3,250 Lapis.

5 (operator's choice, 2026-11-07): about 250 Lapis for all of a story mission's challenges. 416 of the 708
story missions in the first world pay 50 Lapis across their challenges (238 pay 30); 50 x 5 = 250.
"""
from __future__ import annotations

import os


def multiplier() -> float:
    try:
        return max(0.0, float(os.environ.get("EXVIUS_LAPIS_MULTIPLIER", "5")))
    except ValueError:
        return 5.0


def earned(amount: int) -> int:
    """`amount` of earned Lapis after the multiplier."""
    amount = int(amount)
    return amount if amount <= 0 else int(round(amount * multiplier()))


def _int(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


def daily_quest_lapis() -> int:
    return _int("EXVIUS_DAILY_QUEST_LAPIS", 150)


def daily_all_bonus() -> int:
    return _int("EXVIUS_DAILY_ALL_BONUS", 200)


def weekly_gift() -> list[tuple[int, int, int]]:
    out = []
    for part in os.environ.get("EXVIUS_WEEKLY_GIFT", "23:50:10,23:70:1").split(","):
        bits = part.strip().split(":")
        if len(bits) == 3 and all(b.isdigit() for b in bits):
            out.append((int(bits[0]), int(bits[1]), int(bits[2])))
    return out


WEEKLY_GIFT_TITLE = "Weekly Summon Gift"


def deliver_weekly_gift(spec, reply_id):
    """Mail this week's summon gift once per summon-rotation week (same carrier as the other mails)."""
    from ffbe_state import State
    from ffbe_config import ANNIVERSARY_TICKET_CARRIER
    gift = weekly_gift()
    if (not gift or reply_id not in ANNIVERSARY_TICKET_CARRIER.split(",") or State.player is None
            or not isinstance(spec, dict) or State.player.mode == "frozen"):
        return spec
    try:
        import gacha_rotation
        week = int(gacha_rotation.week()[0])
    except Exception:  # noqa: BLE001
        return spec
    state = State.player.data.setdefault("weekly_gift", {})
    if int(state.get("last_week", -1)) >= week:
        return spec
    state["last_week"] = week
    State.player.dirty = True
    State.player.deliver_mail(
        WEEKLY_GIFT_TITLE, gift, mail_id=str(920000000000 + week),
        message="This week's summon gift: a 10+1's worth of tickets. Use them with any banner's "
                "Ticket Summon button.",
        icon_type=2, attach_type=1)
    print(f"weekly gift: week {week} mailed {gift}", flush=True)
    return spec
