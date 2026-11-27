# Security

## What this tool can touch

- **Network:** only `forever setup`, `update`, `item` and `quest` make requests, for public game data, and only
  over HTTPS to `foreverdb.net`, `wago.tools` and `nether.wowhead.com`: a request or a redirect to anything else
  (another host, plain http) is refused. Answers have size caps (8 MB for a page, 64 MB or the published size for a
  file), every ForeverDB file must match its published SHA-256, and a build number is used only when it looks like
  one. `forever me`, `forever price` and `forever where` make none. `--offline` (or `FOREVER_OFFLINE=1`) turns all
  requests off.
- **Files written:** `Interface/AddOns/ForeverBridge/` (two files) in your game folder, never through a linked
  ForeverBridge folder or file; a linked Interface or AddOns folder that leaves the game folder needs --force (or
  your yes), and the toolkit's own add-on folder is never written to or deleted. Also this tool's own cache and
  config folders: `config.json`, `launcher.txt` and `levels.json` (which `forever me` updates when your game shows
  a new level's experience bar), the downloaded data, and a `.mariachi-forever-guide` marker. A folder becomes the
  tool's only when it holds none of those names yet; a folder that already holds one without the marker is
  someone else's and is never marked, written to or cleaned. `setup --uninstall` removes exactly the two add-on
  files and its own leftover temporary files (setup removes those too) and, in the marked folders only, the tool's
  own files by name; a folder goes only when it is then empty.
- **Files read:** the ForeverBridge.lua and Auctionator.lua saved-variables files (no other add-on's file), the
  game's `.build.info` and quest cache, and the tool's own `config.json`, `levels.json` and (if you made one)
  `wishlist.txt`. To find the game folder it looks in the usual install places (a folder search under your home,
  the Wine, Lutris, Bottles and Steam prefixes) and, on Windows, three registry keys of the game's installer
  (Blizzard Entertainment\World of Warcraft InstallPath, also under WOW6432Node, and its Uninstall entry's
  InstallLocation), read-only. Everything read from disk or the network is parsed as data (Lua tables, CBOR, CSV,
  JSON); nothing is ever run. Printed paths show your home folder as `~` and the WoW account folder as
  `<account>`, except the one line of setup that you paste into Claude Code (the toolkit folder, in full), and
  when you set FOREVER_DEBUG=1 yourself.
- **Credentials:** none. There is no login, token or API key anywhere in this repository. Claude runs in your own
  Claude Code with your own sign-in, which this tool never sees.
- **The add-on** records only your own character, never chat, whispers or other players, and cannot reach the
  internet (WoW add-ons cannot).

## Reporting a problem

Please report a security problem privately: open a GitHub security advisory on this repository ("Security" tab,
"Report a vulnerability"). Do not put personal data, account names or saved-variables files in a public issue.
The maintainer tries to answer within a week.
