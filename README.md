# Mariachi Code, Forever Guide

Your own WoW Forever character and Forever's own game data, in plain text, for you and for Claude.
Powered by Claude, in your own Claude Code.

**Download (one link):** https://github.com/KrasimirKralev/mariachi-forever-guide/releases/latest/download/mariachi-forever-guide.zip
(one zip for Windows, Linux and macOS; every version and its SHA-256: https://github.com/KrasimirKralev/mariachi-forever-guide/releases/latest)

## What it is

Three small pieces that work together:

- **ForeverBridge**, an in-game add-on. When you `/reload` or log out, the game writes your character to one local
  file: level, XP, gold, where you are, worn items with their real stats, professions, reputation, quests done and
  in the log, talents, bags, and the recipes, trainers and vendors you have opened.
- **`forever`**, a command line. It reads that file and answers from Forever's own data: items, quests, places,
  vendors, trainers, auction prices from your own Auctionator scans, and the XP budget of a twink. Every answer
  says which data it came from and how old it is. Classic data is used only where Forever's own data says
  nothing, and it is always labelled "Classic data".
- **forever-guide**, a Claude Code plugin. Its skill teaches Claude to use `forever`: check how old your snapshot
  is, price every buy list, look up which quests you have already done, explain the XP left before level 29.

No game files, art or data tables are shipped, with one small exception: eleven Classic experience-per-level
numbers (levels 20 to 30) are built in for the XP budget, and every answer that uses them is labelled Classic data
(your own game replaces each one as soon as it shows that level). Also built in, as rules and names rather than
content: the five-step rule for quests below your level (from ForeverDB.net's data legend) and the client's slot,
quality and standing lists. `setup` and `update` download Forever's data (the lookups fetch single tooltips)
into your own cache folder, with credit to ForeverDB.net, wago.tools and Wowhead (see [NOTICE.md](NOTICE.md)).

## Quick start

You need Python 3.9 or newer ([python.org](https://www.python.org/downloads/); on Windows tick "Add to PATH") and
WoW Forever. Auctionator is optional (for prices). Claude Code is needed only for step 3.

1. **Download the zip** from the link above and unzip it anywhere.
2. **Open a terminal in that folder and run** `python forever setup` (on Windows `py forever setup`, on macOS
   and Linux `python3 forever setup`). It finds the game folder (or asks you for it), copies the add-on into
   `Interface/AddOns/ForeverBridge`, downloads Forever's data (about 15 files, 12 MB) and prints the next steps:
   restart the game, then type `/fbridge save` once you are in.
3. **Add the Claude plugin and ask.** Install [Claude Code](https://docs.claude.com/en/docs/claude-code), sign in
   with your own Claude account (`claude login`), then inside Claude Code:

   ```
   /plugin marketplace add KrasimirKralev/mariachi-forever-guide
   /plugin install forever-guide@mariachi-forever-guide
   ```

   (Offline, or before the repository is public: `/plugin marketplace add <the unzipped folder>` works too.)
   Now ask.

### Questions to ask Claude

- "How much XP can I still earn before level 29, and what is my quest log worth?"
- "What do I need to buy to get Tailoring from 100 to 125, and what does it cost at my auction house?"
- "Have I already done the quests for the dungeon I want to run tonight?"
- "Which slots are empty, and which of these items do I already have?"
- "Where is a Tailoring trainer for the Horde, and which vendor sells the thread I need?"

### Or use it yourself

```
python forever me                    # who, level, XP, gold, where, professions
python forever me status             # how old the snapshot is, and what the add-on could not read
python forever me gear | stats | skills | recipes | trainer | vendor | rep | quests | bags | missing | xp | talents | json
python forever me quests "Quest name" # done, in your log, or not done
python forever me xp --cap 29        # the XP budget before a level cap
python forever price "Item one, Item two"
python forever item "Item name"      # Forever's tooltip, where it drops, who sells it
python forever quest "Quest name"    # level, who gives it and where, XP
python forever where "Name"          # an NPC, a kind of vendor, an item sold by vendors, or a zone
python forever update [--check]      # refresh Forever's data (or only say whether it is current)
python forever version               # version, data and credits
```

Every command takes `--game DIR` (the `_forever_` folder), `--offline` and `--side horde|alliance`.

In the game: `/fbridge` (snapshot age), `/fbridge save` (refresh and write the file now), `/fbridge auto on|off`
(opt-in: reload by itself while you rest in a town, never in combat, at most every 20 minutes), `/fbridge stop`,
`/fbridge diag`.

## Privacy

- **The add-on records only your own character, writes one local file, sends nothing anywhere.** It does not
  record chat, whispers, guild notes, friends or other players. WoW add-ons cannot reach the internet.
- `forever me` and `forever price` read files on your PC and make no network requests at all.
- `forever setup`, `update`, `item` and `quest` download public game data (ForeverDB.net's add-on data files,
  the game client's tables from wago.tools, Wowhead's Forever tooltips) into your cache folder: only over HTTPS,
  only from foreverdb.net, wago.tools and nether.wowhead.com (a redirect anywhere else is refused), at most
  2 requests a second per site, one at a time, with the plain User-Agent `mariachi-forever-guide/<version>`.
  `forever where` downloads nothing. Nothing about you is sent: no character, no account, no file of yours.
  Like any web request it shows your IP address to the site; beyond that the sites see the number of the item,
  quest or creature you look up and your game's build number.
  `--offline` turns all of it off.
- `forever setup` writes only `Interface/AddOns/ForeverBridge/` in your game folder, never through a linked
  ForeverBridge folder or file (a linked Interface or AddOns folder that leaves the game folder needs --force),
  plus this tool's own config and cache folders. It never touches other add-ons, your accounts or WTF settings.
  `python forever setup --uninstall` removes the add-on (`--purge` also removes the downloaded data).
- When you use Claude, Claude reads the text `forever` prints, in your own Claude Code session.

## How Claude is used

The Guide uses **your own Claude Code sign-in**: sign in once with `claude login`, the same way Claude Code itself
works. Claude runs in your Claude Code; the plugin adds a skill (instructions) and the `forever` command to it.
Nothing in this repository asks for, reads or stores a Claude login, token or API key: the Guide never sees it.

## Troubleshooting

| What you see | What to do |
| --- | --- |
| ForeverBridge is not in the game's add-on list | Quit the game fully and start it again (new add-ons load only then). On the character screen, AddOns: tick ForeverBridge and "Load out of date AddOns". |
| `No snapshot yet` | In the game type `/fbridge save` (or log out once). |
| `forever me status` warns there is no gear or no completed quests | The snapshot was written at a logout while the game had already emptied them. Type `/fbridge save` in the game. |
| `game folder: not found` | Run `python forever setup --game "<the folder that holds _forever_>"`, or set `FOREVER_GAME_DIR`. |
| Setup says the folder is not named `_forever_` | Point it at the `_forever_` folder. Add `--force` only if that folder really is WoW Forever. |
| Setup says a folder is a link | It never writes through a linked `Interface/AddOns/ForeverBridge`: remove that link, then run setup again. If `Interface` or `AddOns` itself leads outside the game folder (another drive, say), add `--force` once you are sure. |
| A download stopped half-way | Run `python forever update` again: it goes on with what is missing (finished files are kept; a half-fetched game table starts again). |
| After a game patch | `python forever update --check` says whether the data matches your game; `python forever update` refreshes it. |
| No prices | Install Auctionator, open the auction house and let it scan, then `/reload`. |
| Claude says `forever` is not found | Run `python forever setup` once in the unzipped folder (it tells the plugin where the folder is), then restart Claude Code. If you moved the folder, run setup again. |
| You are behind a proxy | Set `HTTPS_PROXY`; Python uses it. |

Your data lives in your own folders: the cache in `%LOCALAPPDATA%\mariachi-forever-guide\Cache` (Windows),
`~/Library/Caches/mariachi-forever-guide` (macOS) or `~/.cache/mariachi-forever-guide` (Linux), the config in
`%APPDATA%`, `~/Library/Application Support` or `~/.config`. `FOREVER_CACHE_DIR` and `FOREVER_CONFIG_DIR` move them;
each folder the tool uses carries a `.mariachi-forever-guide` marker, and uninstall removes only the tool's own
files from a marked folder, nothing else that is in it.

## Credits

Data from ForeverDB.net (https://foreverdb.net). Game tables of the WoW Forever client from wago.tools. Item, quest
and NPC tooltips from Wowhead's public tooltip service. Classic data from CMaNGOS classic-db, as ForeverDB.net
ships it. Full credits and licences: [NOTICE.md](NOTICE.md). `forever version` prints them too.

Not affiliated with or endorsed by Blizzard Entertainment or Anthropic. World of Warcraft is a trademark of
Blizzard Entertainment, Inc.; Claude is a trademark of Anthropic, PBC.

## Licence

The code is MIT licensed ([LICENSE](LICENSE)). The data the tool downloads for you is not part of this repository
and keeps its own terms ([NOTICE.md](NOTICE.md)).
