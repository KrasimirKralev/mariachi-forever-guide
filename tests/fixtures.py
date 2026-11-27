"""Tiny synthetic fixtures. Every name, id and number in here is invented: they only copy the SYNTAX of the files
the tools read (ForeverDB.net's add-on data files, wago.tools CSV tables, WoW saved variables, Auctionator's CBOR,
the client's quest cache), never their content.
"""
import os
import struct
import tempfile
import time

# ---- ForeverDB-like add-on data files --------------------------------------------------------------------------
HEADER = '-- Synthetic test data in the layout of an add-on data file.\nlocal _, ns = ...\n'

FDB = {
    'Meta.lua': HEADER + 'ns.meta = {version="2030-01-01.test",built=1700000000,build="9.9.9.12345",cap=60,site="https://example.invalid"}\n',
    'QuestForever.lua': HEADER + '''-- [quest] = "title|level|min level|objective|starts|ends|players|new|after|seen min|side|offer floor|classes"
ns.qfQuests = {
[990001]="Mock Quest|35|25|Bring 5 Mock Silks to Trainer Tom in Mockzone.|n980001|n980002|120|1|990005|24|h|24|",
[990005]="Mock Prelude|30|20|Speak with Trainer Tom.|n980001|n980001|80|0|0|20|h|20|",
[990006]="Twin Quest|20|0|Do a \\"quoted\\" thing.|o970001|n980003|3|0|0|0|a|0|",
}
ns.qfPoi = {
[990001]={s="4jr6bq1",e="4jrgvcw"},
}
ns.qfSeen = {
[990005]={s="4jqx31o",e="4jqx31o",o={[1]="4jr6bq1"}},
}
ns.qfTwin = {
[990006]="990007",
}
ns.qfNpcNames = {
[980001]="Trainer Tom",
[980002]="Ender Ella",
}
ns.qfNpcSpots = {
[980002]="4jrgvcw",
[980001]="4jr6bq2",
}
ns.qfItems = {
[900030]="Quest Trinket",
}
''',
    'QuestClassic.lua': HEADER + '''-- [quest] = "title|level|min|side|classes|races|need all|need one|excl|starts|ends|objectives|skill|flags|rep|breadcrumb"
ns.qcQuests = {
[990001]="Mock Quest|36|27|h|0|0||||n980001|n980002|c:1:5||||",
[990002]="Old Classic Quest|22|18|h|0|0|990005 990001|||n980004|n980004|c:1:5||||",
}
ns.qcNpc = {
[980004]="Classic Carl|4jroyac",
[980001]="Trainer Tom|4jqx31o",
[980003]="Twin Keeper|4jroyac",
}
ns.qcObj = {
[970001]="Mock Chest|4jqx31o",
}
''',
    'QuestXP.lua': HEADER + '''ns.qxp = {
q={[990001]=8200,[990005]=1200,[990002]=900},
curve={11,22,33,44,55},
dmul=1.5,
src="test",
}
''',
    'NPCs.lua': HEADER + '''ns.npcs = {[980001]={"Trainer Tom","Tailoring Trainer",9901,63.1,44.9,"H",1},[980005]={"Vera Vendor","Trade Supplies",9902,40.0,60.0,"H",1},[980006]={"Alice Ally","Trade Supplies",9902,10.0,10.0,"A",0}}
ns.sold = {[920001]={980005,50,1,0,980006,45,1,0}}
ns.soldNames = {[920001]="Mock Salt",[920002]="Vendor Only Thread"}
ns.soldCount = {[920001]=3}
''',
    'GearSources.lua': HEADER + '''ns.gfItemText = [==[
jag1|Mock Silk Cap|q|s|h|||c^Tailoring^125^x^s
jag4|Mock Wand|q|s|h|||q^990001^Mock Quest^1^h^s~V^980005^25000^x^s~d^980010^Boss Bramble^2.5^x^k
jahe|Mock Relic|q|s|h|||R^980010^Boss Bramble^0^s
jahf|Mock Charm|q|s|h|||q^990001^Mock Quest^1^h^s~R^980010^Boss Bramble^0^s
]==]
''',
    'Loot.lua': HEADER + '''ns.lootDB = {
  v = 1,
  inst = {
    { id = 1, name = "Mock Depths", kind = "dungeon", lv = "20-25", zone = 9901,
      bosses = {
        { npc = 980010, name = "Boss Bramble", loot = "900010:12.5:f:2:40;900011:3:c" },
      },
      trash = "920003:0:f:::4",
    },
  },
}
''',
    'SearchNames.lua': HEADER + 'ns.searchItemNames={[900001]="Name From Search",[900020]="Server Only Gem",[920001]="Mock Salt"}\n',
}

# ---- wago.tools-like CSV tables --------------------------------------------------------------------------------
WAGO = {
    'ItemSparse': 'ID,Description_lang,Display_lang,OverallQualityID,ItemLevel,RequiredLevel,InventoryType\n'
                  '900001,,Mock Silk Cap,3,30,25,1\n'
                  '900004,,Mock Wand,2,28,23,15\n'
                  '900010,,Glimmer Widget,2,20,15,12\n'
                  '900011,,Glimmer Widget,3,35,30,12\n'
                  '920001,,Mock Salt,1,5,0,0\n'
                  '920003,"A dye, with a comma",Mock Dye,1,10,0,0\n'
                  '900099,,,1,1,1,0\n',
    'SpellName': 'ID,Name_lang\n930010,Mock Aim\n930001,Mock Bolt of Silk\n',
    'SpellItemEnchantment': 'ID,Name_lang,EffectPointsMin_0,EffectPointsMin_1,EffectPointsMin_2\n'
                            '8001,Agility +$k1,4,0,0\n8002,Armor +$k1 and Power +$k2,16,4,0\n',
    'UiMap': 'Name_lang,ID,ParentUiMapID,Flags,System,Type\nMock Continent,9900,0,0,0,2\nMockzone,9901,9900,0,0,3\n'
             'Testvale,9902,9900,0,0,3\nMock City,9903,9901,0,0,3\n',
    'UiMapAssignment': 'UiMin_0,UiMin_1,UiMax_0,UiMax_1,Region_0,Region_1,Region_2,Region_3,Region_4,Region_5,ID,UiMapID,'
                       'OrderIndex,MapID\n0,0,1,1,0,0,0,1000,1000,0,1,9901,0,1\n0,0,1,1,2000,2000,0,3000,3000,0,2,9902,0,1\n'
                       '0,0,1,1,600,600,0,700,700,0,3,9903,0,1\n',
    'TaxiNodes': 'Name_lang,Pos_0,Pos_1,Pos_2,ID,ContinentID,Flags\nMock Post Mockzone,500,250,0,501,1,2\n'
                 'Ally Dock Testvale,2500,2500,0,502,1,1\nMock City Tower,650,650,0,503,1,2\n',
}


def write_raw(root):
    """Write the synthetic downloads into root/raw/{wago/<build>,foreverdb}; returns (wago dir, foreverdb dir)."""
    wago = os.path.join(root, 'raw', 'wago', '9.9.9.12345')
    fdb = os.path.join(root, 'raw', 'foreverdb')
    os.makedirs(wago, exist_ok=True)
    os.makedirs(fdb, exist_ok=True)
    for name, text in WAGO.items():
        with open(os.path.join(wago, name + '.csv'), 'w', encoding='utf-8', newline='') as fh:
            fh.write(text)
    for name, text in FDB.items():
        with open(os.path.join(fdb, name), 'w', encoding='utf-8') as fh:
            fh.write(text)
    return wago, fdb


# ---- the client's quest cache (questcache.wdb layout) ----------------------------------------------------------
def quest_cache_bytes(records):
    """records: {quest: (level, min level, next, xp multiplier)} -> bytes in the cache's layout."""
    out = bytearray(b'TSQW' + struct.pack('<I', 12345) + b'SUne' + struct.pack('<III', 0, 0, 0))
    for qid, (lv, mn, nxt, mult) in records.items():
        f = [qid, 0, lv, 0, mn, 0, 0, 0, 0, nxt, 0]
        body = struct.pack('<11i', *f) + struct.pack('<f', mult) + b'Mock text\x00'
        out += struct.pack('<II', qid, len(body)) + body
    bad = struct.pack('<12i', 1, 0, 999, 0, 0, 0, 0, 0, 0, 0, 0, 0)  # id mismatch and level 999: skipped
    out += struct.pack('<II', 7, len(bad)) + bad
    return bytes(out)


# ---- WoW saved-variables writer (the game's own layout: ["key"] = value, and -- [n] after array items) ---------
def _key(k):
    return '[%d]' % k if isinstance(k, int) else '["%s"]' % _esc(k)


def _esc(s):
    return s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')


def _value(v, indent, lines, key=None, index=None):
    pre = (_key(key) + ' = ') if key is not None else ''
    post = (', -- [%d]' % index) if index is not None else ','
    if isinstance(v, dict) or isinstance(v, list):
        lines.append(pre + '{')
        if isinstance(v, list):
            for n, item in enumerate(v, 1):
                _value(item, indent + 1, lines, index=n)
        else:
            for k in sorted(v, key=lambda k: (isinstance(k, str), k)):
                _value(v[k], indent + 1, lines, key=k)
        lines.append('}' + post)
    elif isinstance(v, bool):
        lines.append(pre + ('true' if v else 'false') + post)
    elif isinstance(v, (int, float)):
        lines.append(pre + (repr(v) if isinstance(v, float) else str(v)) + post)
    elif isinstance(v, str):
        lines.append(pre + '"' + _esc(v) + '"' + post)


def saved_variables(name, obj):
    lines = ['', name + ' = {']
    for k in sorted(obj, key=lambda k: (isinstance(k, str), k)):
        _value(obj[k], 1, lines, key=k)
    lines.append('}')
    return '\r\n'.join(lines) + '\r\n'


def snapshot(now=None, empty_at_logout=False):
    now = time.time() if now is None else now
    char = {
        'name': 'Testa', 'realm': 'Mockrealm', 'level': 22, 'class': 'WARLOCK', 'classLocal': 'Warlock',
        'race': 'Undead', 'faction': 'Horde', 'xp': 9000, 'xpMax': 27300, 'rested': 5000, 'money': 123456,
        'saved': int(now - 3600),
        'reason': 'save',
        'position': {'zone': 'Mockzone', 'sub': 'Mock Square', 'map': 9901, 'x': 63.1, 'y': 44.9},
        'equipped': [
            {'slot': 'Head', 'id': 900001, 'name': 'Mock Silk Cap', 'ilvl': 30, 'dur': 40, 'durMax': 60,
             'stats': {'ITEM_MOD_AGILITY_SHORT': 8, 'ITEM_MOD_STAMINA_SHORT': 6, 'RESISTANCE0_NAME': 67}},
            {'slot': 'Chest', 'id': 900040, 'name': 'Mock Vest', 'enchant': 8002, 'dur': 5, 'durMax': 60},
            {'slot': 'Ranged', 'id': 900004, 'name': 'Mock Wand', 'enchant': 8001},
        ],
        'stats': {'agility': 80, 'stamina': 60, 'attackPower': 120, 'rangedAttackPower': 180, 'rangedCrit': 6.25,
                  'ranged': {'speed': 2.4, 'min': 32, 'max': 61}},
        'skills': {'lines': [], 'professions': [{'name': 'Tailoring', 'rank': 110, 'max': 150},
                                                {'name': 'Enchanting', 'rank': 80, 'max': 150}]},
        'reputation': [{'name': 'Mock Outriders', 'standing': 5, 'min': 3000, 'max': 9000, 'value': 4200}],
        'quests': {'active': [{'id': 990001, 'title': 'Mock Quest', 'level': 35, 'complete': True},
                              {'id': 990002, 'title': 'Old Classic Quest', 'level': 22},
                              {'id': 990009, 'title': 'Unrecorded Quest', 'level': 22}],
                   'completed': [990005, 990007]},
        'talents': {'tabs': [{'name': 'traits', 'talents': [{'node': 10, 'rank': 3, 'max': 5, 'spell': 930010}]}]},
        'bags': {920001: 20, 900010: 1},
        'tradeskills': {'Tailoring': {'rank': 100, 'max': 150, 'saved': int(now - 7200), 'recipes': [
            {'id': 930001, 'name': 'Mock Bolt of Silk', 'learned': True, 'diff': 2, 'reagents': [[920001, 1]]},
            {'id': 930002, 'name': 'Mock Belt', 'learned': True, 'diff': 0, 'reagents': [[920003, 2]]},
            {'id': 930003, 'name': 'Mock Silk Cap', 'learned': False, 'src': 'Drop: Boss Bramble'}]}},
    }
    if empty_at_logout:
        char.update({'equipped': [], 'bags': {}, 'reason': 'logout', 'xp': 0, 'xpMax': 0, 'money': 0,
                     'stats': {'agility': 0, 'stamina': 0, 'armor': 0, 'mana': 1005}})
        char['quests'] = {'active': char['quests']['active'], 'completed': []}
    return {
        'schema': 1, 'auto': False,
        'chars': {'Testa-Mockrealm': char},
        'trainers': {'980001': {'name': 'Trainer Tom', 'zone': 'Mockzone', 'x': 63.1, 'y': 44.9, 'saved': int(now - 600),
                                'services': [{'name': 'Mock Belt', 'reqSkill': 'Tailoring', 'reqRank': 100, 'cost': 250}]}},
        'vendors': {'980005': {'name': 'Vera Vendor', 'zone': 'Testvale', 'x': 40.0, 'y': 60.0, 'saved': int(now - 600),
                               'items': [{'name': 'Mock Salt', 'price': 50}, {'name': 'Pattern: Mock Kit', 'price': 500, 'limited': 1}]}},
        'diag': {'addon': '1.1', 'game': {'version': '9.9.9', 'build': '12345', 'toc': 16001}, 'has': {'C_Map': True, 'GetNumSkillLines': False}},
        'notes': {'trainer': {'event': 'TRAINER_SHOW', 'ok': True, 'count': 1}},
        'events': {'TRAINER_SHOW': {'n': 1}},
    }


# ---- Auctionator: a CBOR price table inside a Lua string -------------------------------------------------------
def cbor_encode(v):
    def head(major, n):
        if n < 24:
            return bytes([major << 5 | n])
        for ai, size in ((24, 1), (25, 2), (26, 4), (27, 8)):
            if n < 1 << (8 * size):
                return bytes([major << 5 | ai]) + n.to_bytes(size, 'big')
        raise ValueError(n)
    if v is True:
        return b'\xf5'
    if v is False:
        return b'\xf4'
    if v is None:
        return b'\xf6'
    if isinstance(v, int):
        return head(0, v) if v >= 0 else head(1, -1 - v)
    if isinstance(v, float):
        return b'\xfb' + struct.pack('>d', v)
    if isinstance(v, str):
        b = v.encode('utf-8')
        return head(3, len(b)) + b
    if isinstance(v, bytes):
        return head(2, len(v)) + v
    if isinstance(v, list):
        return head(4, len(v)) + b''.join(cbor_encode(x) for x in v)
    if isinstance(v, dict):
        return head(5, len(v)) + b''.join(cbor_encode(k) + cbor_encode(x) for k, x in v.items())
    raise TypeError(type(v))


def as_bytes(v):
    """Auctionator's own encoder writes every Lua string as a CBOR byte string (major type 2): do the same."""
    if isinstance(v, str):
        return v.encode('utf-8')
    if isinstance(v, dict):
        return {as_bytes(k): as_bytes(x) for k, x in v.items()}
    return v


def auctionator_lua(now=None):
    from forever.prices import day_number
    now = time.time() if now is None else now
    day = day_number(now)
    prices = {
        '920001': {'m': 53, 'l': {str(day - 2): 48, str(day): 50}, 'h': {str(day): 60}, 'a': {str(day): 31}},
        'g:900011:35': {'m': 25000, 'l': {str(day - 5): 21000}, 'a': {str(day - 5): 2}},
        '900010': {'m': 1500, 'h': {str(day - 1): 1700}},
    }
    raw = cbor_encode(as_bytes(prices))
    # the game writes the bytes as they are, escaping only backslash, quote and line breaks
    s = raw.decode('latin-1').replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')
    return ('\r\nAUCTIONATOR_PRICE_DATABASE = {\r\n["__dbversion"] = 8,\r\n["Mock Realm"] = "' + s + '",\r\n}\r\n'
            'AUCTIONATOR_CONFIG = {\r\n["x"] = 1,\r\n}\r\n').encode('latin-1')


# ---- a fake game folder -----------------------------------------------------------------------------------------
def fake_game(root, snapshot_obj=None, variable='ForeverBridgeDB', filename='ForeverBridge.lua', prices=True,
              quest_cache=True):
    """root/World of Warcraft/_forever_ with a build file, Wow.exe, one account's saved variables and a quest cache."""
    wow = os.path.join(root, 'World of Warcraft')
    game = os.path.join(wow, '_forever_')
    sv = os.path.join(game, 'WTF', 'Account', 'TESTACCOUNT', 'SavedVariables')
    os.makedirs(sv, exist_ok=True)
    os.makedirs(os.path.join(game, 'Interface', 'AddOns', 'SomeoneElsesAddon'), exist_ok=True)
    with open(os.path.join(game, 'Interface', 'AddOns', 'SomeoneElsesAddon', 'Other.toc'), 'w') as fh:
        fh.write('## Title: Other\n')
    with open(os.path.join(game, 'Wow.exe'), 'wb') as fh:
        fh.write(b'')
    with open(os.path.join(wow, '.build.info'), 'w', encoding='utf-8') as fh:
        fh.write('Branch!STRING:0|Active!DEC:1|Version!STRING:0|Product!STRING:0\n'
                 'eu|0|9.9.8.11111|wowf\neu|1|9.9.9.12345|wowf\neu|1|1.0.0.10001|wow\n')
    if snapshot_obj is not False:
        with open(os.path.join(sv, filename), 'w', encoding='utf-8', newline='') as fh:
            fh.write(saved_variables(variable, snapshot_obj or snapshot()))
    if prices:
        with open(os.path.join(sv, 'Auctionator.lua'), 'wb') as fh:
            fh.write(auctionator_lua())
    if quest_cache:
        wdb = os.path.join(game, 'Cache', 'WDB', 'enUS')
        os.makedirs(wdb, exist_ok=True)
        with open(os.path.join(wdb, 'questcache.wdb'), 'wb') as fh:
            fh.write(quest_cache_bytes({990001: (36, 26, 990010, 2.4), 990002: (22, 17, 0, 1.0)}))
    return game


class TempEnv:
    """A temp HOME, cache and config, offline: nothing in a test can reach the real home or the network."""
    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='fg-test-')
        self.root = self.tmp.name
        self.env = {'HOME': os.path.join(self.root, 'home'), 'FOREVER_OFFLINE': '1',
                    'FOREVER_CACHE_DIR': os.path.join(self.root, 'cache'),
                    'FOREVER_CONFIG_DIR': os.path.join(self.root, 'config')}
        os.makedirs(self.env['HOME'])
        self.saved = {k: os.environ.get(k) for k in list(self.env) + ['FOREVER_GAME_DIR', 'XDG_CACHE_HOME', 'XDG_CONFIG_HOME', 'WINEPREFIX']}
        for k in ('FOREVER_GAME_DIR', 'XDG_CACHE_HOME', 'XDG_CONFIG_HOME', 'WINEPREFIX'):
            os.environ.pop(k, None)
        os.environ.update(self.env)
        return self

    def __exit__(self, *exc):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()
