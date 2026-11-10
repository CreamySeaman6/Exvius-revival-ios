# Changelog

Each entry is one update to this repo. To update: in your repo folder run `git pull`, then from `ios-server` run `docker compose build && docker compose up -d`. Your save isn't touched. Open the game twice afterwards so it picks up the new data.

## 2026-11-10 (third update)

- Collection points in explorations now show up (the sparkling spots; Dalnakya Cavern has three) and give what they gave in Global: ore, Lumber, crysts or magicite, or the event's own items in event explorations.
- What you collect shows on the result screen and lands in your bag when you leave the exploration.

## 2026-11-10 (second update)

- Story units (Rain, Lasswell, Fina, Lid, Nichol, Sakura, Jake) and event reward units no longer show up in normal summons.
- Story units now join as you reach them in the story. Saves already past that point get them at the next login.
- Extra copies of story units you already pulled can be sold now.

## 2026-11-10

- Random battles are actually random now. Chamber of Awakening 5★ was only ever dropping Hard Rocks and Fury Seeds because of this, along with about 1,300 other quests.
- Enemy drop tables filled in from Global's records, so some quests that dropped nothing now drop stuff.
- Event currency (Candy etc.) drops in battle like it used to, boosted since there are no packs to buy.
- King Mog exchange shops are back.
- First clear rewards actually pay out now. If you've already cleared quests, check your gift box for a "First-Clear Rewards" mail.
- Some event rewards corrected to match Global's original runs, and missing challenges restored.
- Raid summons and box summons added. They show up when the replay reaches each raid.
- Fixed the Windows / Docker Desktop `exec /app/entrypoint.sh: no such file or directory` error.
