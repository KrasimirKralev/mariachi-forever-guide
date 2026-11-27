# Notices and credits

The code in this repository is MIT licensed (see `LICENSE`). **No game files, art, fonts, icons, maps, tooltips or
data tables are in this repository or in its release zip**, with one small exception: eleven Classic
experience-per-level numbers (levels 20 to 30) from World of Warcraft Classic are built into `forever/snapshot.py`
for the XP budget, and every answer that uses one is labelled Classic data. Also built in, as rules and names
rather than content: the five-step rule for quests below your level (from ForeverDB.net's data legend) and the
client's slot, quality and standing lists. Of the commands, only `forever setup` and `forever update` download the
data below (the lookups fetch single tooltips), into your own cache folder, unmodified,
politely (HTTPS only, from foreverdb.net, wago.tools and nether.wowhead.com only, one request at a time, at most 2
a second per site, the User-Agent `mariachi-forever-guide/<version>`, cached; a stopped update goes on with what is
missing). It builds a local
database from it on your PC. `forever version` prints these credits.

## Data from ForeverDB.net (https://foreverdb.net)

**Data from ForeverDB.net (https://foreverdb.net).** Quests, quest givers and where they stand, quest experience,
vendors and their prices, trainers, item sources and loot come from ForeverDB.net's add-on data files
(`https://foreverdb.net/downloads/addon-manifest.json`; each file is checked against its published SHA-256, and a
file without one is not taken). Their
`robots.txt` names this manifest as the place for apps, add-ons and tools.

ForeverDB.net licenses this data under the GNU General Public License v3.0 with an additional attribution term
(GPL-3.0 section 7(b)): keep the line starting `-- Data: ForeverDB.net (https://foreverdb.net)` and the other
notices in every file taken, and show the attribution "Data from ForeverDB.net (https://foreverdb.net)" in the
credits of the work. This tool keeps their files unmodified in your cache, never ships them, and shows that
attribution in `forever version`, in the data line of every lookup (`item`, `quest`, `where`, `me quests "<name>"`,
`me xp`), and here; item names that the other `me` parts and `price` print come from the game's tables and, where
those have none, from ForeverDB's name lists.
Their full
terms are in `LICENSE.txt` and `NOTICE.txt` of the ForeverDB add-on.

Some entries are **Classic data**, derived by ForeverDB.net from **CMaNGOS classic-db**
(https://github.com/cmangos/classic-db, GPL-3.0, Copyright the CMaNGOS project and its contributors). The tool uses
them only where Forever's own data says nothing, and labels every such line "(Classic data)".

## Game tables from wago.tools (https://wago.tools)

Item names, item levels and slots, spell and enchant names, maps and flight points are read from the WoW Forever
client's own tables for your game's build, downloaded as CSV from wago.tools. These names and numbers are
Blizzard Entertainment's.

## Tooltips from Wowhead (https://www.wowhead.com/forever)

Item, quest and NPC tooltips are fetched one at a time, when a lookup needs one, from Wowhead's public tooltip service
(`nether.wowhead.com/forever/tooltip/...`) and kept in your cache.

## Your own files

`forever me` reads the ForeverBridge add-on's saved-variables file, `forever price` the Auctionator add-on's, and
`forever update` your game's own quest cache (`Cache/WDB/*/questcache.wdb`), all read-only and only on your PC.
Auctionator is a separate add-on by its own authors; this tool only reads the prices it saved.

## Python

Python's standard library only. Pillow is not used.

## Trademarks

This project is not affiliated with or endorsed by Blizzard Entertainment or Anthropic.
World of Warcraft is a trademark of Blizzard Entertainment, Inc.; Claude is a trademark of Anthropic, PBC.
ForeverDB.net, wago.tools and Wowhead are not affiliated with this project either.
