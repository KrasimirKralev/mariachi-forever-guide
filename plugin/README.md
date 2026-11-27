# forever-guide, the Claude Code plugin of Mariachi Code, Forever Guide

Claude Code only: the plugin carries a `bin/` command, which claude.ai and Cowork do not install. The command is a
POSIX shell script: on Windows, Claude Code runs its commands through Git Bash, which runs it.

This plugin teaches Claude in your own Claude Code to answer WoW Forever questions with the `forever` command
line: your own character from the ForeverBridge add-on (gear, XP, gold, quests done, professions), your own
Auctionator prices, and Forever's own items, quests, vendors, trainers and places, with Classic data only where it
is labelled. It adds one skill (`forever-guide`) and the `forever` command (in `bin/`).

Setup: unzip the Forever Guide, run `python forever setup` in that folder once (it installs the add-on, downloads
the data and tells this plugin where the folder is), then in Claude Code:

```
/plugin marketplace add KrasimirKralev/mariachi-forever-guide
/plugin install forever-guide@mariachi-forever-guide
```

See the README.md of the repository for the full quick start, privacy and
troubleshooting. The plugin never asks for, reads or stores a Claude login or key: it uses your own sign-in.
