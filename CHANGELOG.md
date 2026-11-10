# Changelog

Each entry is one update to this repo. To update: in your repo folder run `git pull`, then from `ios-server` run `docker compose build && docker compose up -d`. Your save isn't touched. Open the game twice afterwards so it picks up the new data.

## 2026-11-10: Vision Cards, Aquapolis hidden

- Vision Cards equipped on Neo Vision units (such as Blade of Vengeance Ibara) now stay equipped; before, the slot looked empty. Loading a saved party no longer takes units' Vision Cards off.
- Memories from the Aquapolis is hidden from the Vortex for now: its stage files were lost, so it had no treasure chests and no proper ending.
- A summoned Neo Vision unit now comes with a random Vision Card from the cards Global had in its summon pool at that point in the replay, like in Global. A unit's own card comes from EX awakening (EX+1 and EX+3), as before.

## 2026-11-10: Faster loading

- The game loads faster: the server no longer asks it to upload its error log over and over (about 22 MB every 15 seconds). Uploads are now off by default; when you turn them on to get a log, the game sends it once per launch. See the README ("Logs from the game itself").

## 2026-11-10: Exchanges follow the replay, unit dates, the Captain

- King Mog and the Mog Minister now trade for the event that is on this week, like in Global (for example Candy during Mana Mystery), instead of always Star Quartz and Auracite Shards. Between events they keep the exchange of an event currency you still have.
- Exchanges on the Shop's summon coin screen show up while their event is on or while you hold their currency. The Star Quartz unit exchanges appear when the replay reaches January 2023, when Global added them.
- Events only show the quests they had at that point in the replay. Trials and stages a later run added (for example Chamber of the Vengeful's later trials) appear when the replay reaches them, so their rewards and exchanges no longer show up early.
- Orbonne Monastery Vaults' enemies drop Auracite Shards while the event is on, for the Mog Minister's exchange.
- The Vortex lists story and limited-time events at the top and the farming chambers at the bottom.
- Fixed units showing up in summons later than they came out on Global, such as Gilgamesh (FFV), who now appears from the start. 187 units' release dates were checked against Global's own history and moved earlier.
- The units Global launched with can be summoned from the start, including Roselia, Miyuki, Gilbert, Xiao, Firion, Maria, Vaan, Penelo, Shantotto and Fran.
- Limited-time, collaboration and seasonal units no longer show up in regular summons. Like in Global, they only come from the summons that feature them.
- The Moogle Guard Captain in the Vortex town now trades for leftover event currency: his menu lists the exchanges for currency you still hold that King Mog and the Mog Minister aren't showing this week, plus his own Super Trust Moogle and Dark Visions exchanges once the replay reaches them. Future and empty exchanges are gone. His menu updates each time you start the game.
- Exchanges now show the name of the merchant you opened them from: the Mog Minister no longer says he's King Mog, and the Captain's exchanges show the Captain.
- The Vortex town is no longer downloaded again every time you enter it.
- The Captain's exchanges show the right currency icon instead of a Star Quartz-like crystal.
- The Shop's exchange list and King Mog, the Mog Minister and the Captain now share one stock: an item limited to 2 can be bought twice in total, like in Global, not twice in each place.
- Unit pictures on the News notices and the summon Drop Rates pages now come from the game's own files instead of the Brave Exvius wiki, so Neo Vision and other 7★ units (Sol -Neo Vision-, Summoner Yuna, Sora (KHIII) and more) show a picture instead of a grey box.

## 2026-11-10: Collection points

- Collection points in explorations now show up (the sparkling spots; Dalnakya Cavern has three) and give what they gave in Global: ore, Lumber, crysts or magicite, or the event's own items in event explorations.
- What you collect shows on the result screen and lands in your bag when you leave the exploration.

## 2026-11-10: Story units

- Story units (Rain, Lasswell, Fina, Lid, Nichol, Sakura, Jake) and event reward units no longer show up in normal summons.
- Story units now join as you reach them in the story. Saves already past that point get them at the next login.
- Extra copies of story units you already pulled can be sold now.

## 2026-11-10: Random battles, drops, first-clear rewards

- Random battles are actually random now. Chamber of Awakening 5★ was only ever dropping Hard Rocks and Fury Seeds because of this, along with about 1,300 other quests.
- Enemy drop tables filled in from Global's records, so some quests that dropped nothing now drop stuff.
- Event currency (Candy etc.) drops in battle like it used to, boosted since there are no packs to buy.
- King Mog exchange shops are back.
- First clear rewards actually pay out now. If you've already cleared quests, check your gift box for a "First-Clear Rewards" mail.
- Some event rewards corrected to match Global's original runs, and missing challenges restored.
- Raid summons and box summons added. They show up when the replay reaches each raid.
- Fixed the Windows / Docker Desktop `exec /app/entrypoint.sh: no such file or directory` error.
