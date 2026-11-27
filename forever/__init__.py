"""Mariachi Code, Forever Guide: your own WoW Forever character and Forever's own data, as plain text.

Standard library only (Python 3.9+). Nothing in this package asks for, reads or stores a Claude credential:
Claude runs in the player's own Claude Code, signed in with their own account.
"""

VERSION = '0.1.0'
APP = 'mariachi-forever-guide'
PRODUCT = 'Mariachi Code, Forever Guide'
USER_AGENT = APP + '/' + VERSION

CREDITS = (
    'Data from ForeverDB.net (https://foreverdb.net), GPL-3.0 with an attribution term; '
    'its Classic parts from CMaNGOS classic-db (GPL-3.0).',
    "Game tables of the WoW Forever client from wago.tools (https://wago.tools).",
    "Item, quest and NPC tooltips from Wowhead's public tooltip service (https://www.wowhead.com/forever).",
    'Not affiliated with or endorsed by Blizzard Entertainment or Anthropic. World of Warcraft is a trademark '
    'of Blizzard Entertainment, Inc.; Claude is a trademark of Anthropic, PBC.',
)
