# Contributing

Thank you for helping. A few rules keep this repository safe to publish.

## Never commit

- Game files, art, icons, fonts, maps, tooltips, DB2/CSV tables, item or quest data, or anything downloaded from
  ForeverDB.net, wago.tools or Wowhead. The tool downloads those for each player at run time.
- Your own saved-variables files, character names, account names or numbers, paths of your PC, e-mail addresses.
- Binaries, `__pycache__`, `.pyc`, `node_modules`, build output (`dist/`).

Tests use small invented fixtures (`tests/fixtures.py`) that copy only the syntax of those files.

## Before a pull request

```
python3 -I -B -m unittest               # every test: no network, temp folders only
python3 -I -B scripts/scan_private.py --words <your local words file>   # must say: clean, 0 hits
```

The add-on tests need a Lua 5.1-compatible runner (Neovim's `nvim -l`, LuaJIT or Lua 5.1); without one they are
skipped with a message. Python 3.9 is the oldest supported version: standard library only.

## Style

- Python: 4 spaces, single quotes, lines up to 120 characters (test fixture literals may run longer), comments
  that say why.
- Every answer the command line prints says where its data came from and how old it is; Classic data is labelled
  "(Classic data)".
- Error messages are one friendly line for the player; details only with `FOREVER_DEBUG=1`.
- Commits: `type: description` (feat, fix, refactor, docs, test, chore), lower case, imperative.

## Releasing

Set the same version in `forever/__init__.py` (`VERSION`), `plugin/.claude-plugin/plugin.json`,
`.claude-plugin/marketplace.json` and `plugin/bin/forever` (a test fails while they differ), run the scan with your
own `--words` file, then push a tag `v<version>`. The workflow `.github/workflows/release.yml` runs the tests and the
other checks of the scan (it cannot hold your words, and says so), builds the zips and `SHA256SUMS` with
`scripts/package.py`, and publishes them as a GitHub Release with the checksums in its notes;
`releases/latest/download/mariachi-forever-guide.zip` is the one download link.
