-- Runs ForeverBridge.lua against a mock of the game's functions and writes the SavedVariables file the way WoW
-- does. Every name and number here is invented. Usage (any Lua 5.1-compatible runner):
--   nvim --clean --headless -l addon_harness.lua <addon dir> <out file> <modern|legacy|minimal>
--   luajit addon_harness.lua <addon dir> <out file> <variant>
local dir, outfile, variant = arg[1], arg[2], arg[3] or "modern"
unpack = unpack or table.unpack -- the game's Lua is 5.1; let a newer runner work too

local frames, printed = {}, {}
_G.print = function(...)
  local t = {}
  for i = 1, select("#", ...) do t[#t + 1] = tostring((select(i, ...))) end
  printed[#printed + 1] = table.concat(t, " ")
end

function CreateFrame()
  local f = { events = {}, scripts = {} }
  function f:RegisterEvent(e) self.events[e] = true end
  function f:SetScript(n, fn) self.scripts[n] = fn end
  frames[#frames + 1] = f
  return f
end

local function link(id, name, color)
  return string.format("|c%s|Hitem:%d:0:0:0:0:0:0:0:25:0:0:0:0:0:0|h[%s]|h|r", color or "ff0070dd", id, name)
end

-- what the game "has" at a moment; the logout teardown empties these like the real client does
local worn = {}
local completed = { 990002, 990003, 990004 }
local loggedOut = false
local zoneName = "Mockzone"
local function live(v) if loggedOut then return 0 end return v end

local npcGone = false -- a window open with no npc unit and ANOTHER PLAYER targeted
function UnitName(unit)
  if unit == "player" then return "Testa" end
  if unit == "pet" then return "Mockpet" end
  if unit == "npc" and not npcGone then return "Mock Trainer" end
  if unit == "target" then return "Otherplayer" end
end
function GetRealmName() return "Mockrealm" end
local clock = 1700000000
time = function() return clock end
local tickers = {}
-- timers run at once, or wait in a queue when a test needs to see what a timer starts
local queued, queueTimers = {}, false
C_Timer = {
  After = function(_, fn) if queueTimers then queued[#queued + 1] = fn else fn() end end,
  NewTicker = function(_, fn) tickers[#tickers + 1] = fn end,
}
local fireEvent -- set once the add-on is loaded
local trainerOpen, trainerReads, filterFlips = false, 0, 0
trainerEmpty = false
SlashCmdList = {}

local reloaded = false
local resting, combat = false, false
if variant ~= "minimal" then
  function UnitLevel() return 22 end
  function UnitClass() return "Warlock", "WARLOCK" end
  function UnitRace() return "Undead", "Scourge" end
  function UnitFactionGroup() return "Horde" end
  function UnitSex() return 2 end
  -- at logout the real client reports 0 experience, 0 money and 0 for every stat
  function UnitXP() return live(12000) end
  function UnitXPMax() return live(27300) end
  function GetXPExhaustion() return 5000 end
  function GetMoney() return live(123456) end
  function GetBuildInfo() return "9.9.9", "12345", "Jan 1 2030", 16001 end
  function GetZoneText() return zoneName end
  function GetSubZoneText() return "Mock Square" end
  function ReloadUI() reloaded = true end
  function InCombatLockdown() return combat end
  function IsResting() return resting end
  function IsInInstance() return false end
  function UnitAffectingCombat() return combat end
  local casting, channeling, popup = false, false, false
  function UnitCastingInfo(u) if casting and u == "player" then return "Mock Spell" end end
  function UnitChannelInfo(u) if channeling and u == "player" then return "Mock Channel" end end
  local readyCheck, lootRoll = false, false
  StaticPopup1 = { IsShown = function() return popup end }
  ReadyCheckFrame = { IsShown = function() return readyCheck end }
  GroupLootFrame1 = { IsShown = function() return lootRoll end }
  autoBlockers = function(c, ch, p, r, l) casting, channeling, popup, readyCheck, lootRoll = c, ch, p, r, l end
  function UnitIsDeadOrGhost() return false end
  function GetCurrentKeyBoardFocus() return nil end
  UIErrorsFrame = { AddMessage = function() end }
  worn = {
    [1] = link(900001, "Mock Silk Cap"), [2] = link(900002, "Mock Medallion"),
    [9] = "|cff1eff00|Hitem:900003:0:0:0:0:0:0:0:22:0:0:0:0:0:0:Player-1234-0ABCDEF0|h[Mock Armguards]|h|r", [18] = link(900004, "Mock Wand", "ff1eff00"),
    [16] = link(900005, "Mock Mantle"),
  }
  function GetInventoryItemLink(_, slot) return worn[slot] end
  function GetInventoryItemDurability(slot) if worn[slot] then return 40, 60 end end
  function GetInventoryItemCount() return 1 end
  function GetItemInfo(l) return "x", l, 3, 30, 25 end
  function GetItemStats() return { ITEM_MOD_AGILITY_SHORT = 8, ITEM_MOD_STAMINA_SHORT = 6, RESISTANCE0_NAME = 67 } end
  -- the tooltip of a crafted item names its maker, in the client's own language
  C_TooltipInfo = { GetInventoryItem = function() return { lines = { { leftText = "|cffa335eeMock Silk Cap|r" }, { leftText = "+8 Agility" }, { rightText = "x" },
    { leftText = "|cff00ff00<Made by Otherplayer>|r" }, { leftText = "|cff00ff00<Hergestellt von Otherplayer>|r" } } } end }
  function UnitStat(_, i) return live(10 * i), live(12 * i), 2, 0 end
  function UnitArmor() return live(300), live(320) end
  function UnitAttackPower() return 100, 20, 0 end
  function UnitRangedAttackPower() return 150, 30, 0 end
  function GetCritChance() return 5.5 end
  function GetRangedCritChance() return 6.25 end
  function GetDodgeChance() return 4.1 end
  function GetParryChance() return 5 end
  function GetBlockChance() return 0 end
  function UnitRangedDamage() return 2.4, 32, 61 end
  function UnitAttackSpeed() return 2.0 end
  function UnitHealthMax() return 900 end
  function UnitPowerMax() return 700 end
  function UnitExists(u) return u == "pet" and not loggedOut end
  function UnitCreatureFamily() return "Cat" end
  function UnitGUID(u)
    if u == "npc" and not npcGone then return "Creature-0-1-1-1-980001-0000000001" end
    if u == "target" then return "Player-1-0000ABCD" end
  end
  C_Map = {
    GetBestMapForUnit = function() if loggedOut then return nil end return 9901 end,
    GetPlayerMapPosition = function() return { GetXY = function() return 0.631, 0.449 end } end,
  }
  function GetNumTrainerServices()
    trainerReads = trainerReads + 1
    if trainerEmpty then return 0 end
    return 3
  end
  function GetTrainerServiceInfo(i)
    if i == 1 then return "Tailoring", "", "header" end
    if i == 2 then return "Mock Bolt of Silk", "Apprentice", "available" end
    return "Mock Belt", "", "unavailable"
  end
  function GetTrainerServiceCost(i) return i == 2 and 100 or 250 end
  function GetTrainerServiceSkillReq(i) return "Tailoring", i == 2 and 75 or 100 end
  function GetTrainerServiceLevelReq() return 0 end
  function GetTrainerServiceItemLink(i) return "|cff71d5ff|Hspell:" .. (i == 2 and 930001 or 930002) .. "|h[x]|h|r" end
  function ExpandTrainerSkillLine() end
  -- the player's own filter choices in the trainer window: the add-on must put them back
  -- legacy clients answer 1 or nil; the modern variant below answers true or false
  trainerFilters = { available = 1, unavailable = nil, used = nil }
  filtersAreBooleans = false
  function GetTrainerServiceTypeFilter(kind) return trainerFilters[kind] end
  function SetTrainerServiceTypeFilter(kind, on)
    local new
    -- a client with boolean filters takes the argument as a Lua truth value: 0 would switch a filter ON
    if filtersAreBooleans then new = not not on else new = (on == 1 or on == true) and 1 or nil end
    if trainerFilters[kind] ~= new then
      trainerFilters[kind] = new
      filterFlips = filterFlips + 1
      if trainerOpen and fireEvent then fireEvent("TRAINER_UPDATE") end -- the window refreshes its list
    end
  end
  function GetMerchantNumItems() return 2 end
  function GetMerchantItemInfo(i)
    if i == 1 then return "Mock Dye", "tex", 350, 1, -1 end
    return "Pattern: Mock Kit", "tex", 500, 1, 1
  end
  function GetMerchantItemLink(i) return link(i == 1 and 920003 or 920004, i == 1 and "Mock Dye" or "Pattern", "ffffffff") end
  function GetMerchantItemCostInfo() return 0 end
  NUM_BAG_SLOTS, NUM_BANKBAGSLOTS = 4, 7
end

if variant == "modern" then
  trainerFilters = { available = true, unavailable = false, used = false }
  filtersAreBooleans = true
  -- a client whose GetRealmName() is empty, with a table-returning merchant call and an older "Testa-" record
  function GetRealmName() return "" end
  function UnitFullName() return "Testa", "Mockrealm" end
  GetMerchantItemInfo = nil
  C_MerchantFrame = { GetItemInfo = function(i)
    if i == 1 then return { name = "Mock Dye", price = 350, stackCount = 1, numAvailable = -1, hasExtendedCost = false } end
    return { name = "Pattern: Mock Kit", price = 500, stackCount = 1, numAvailable = 1, hasExtendedCost = false }
  end }
  ForeverBridgeDB = { chars = { ["Testa-"] = { stale = true } } }
  function GetProfessions() if loggedOut then return end return 1, nil, nil, nil, 5, nil end
  function GetProfessionInfo(i) return i == 1 and "Tailoring" or "Enchanting", "icon", i == 1 and 100 or 20, 150, 10, 0, i == 1 and 165 or 185 end
  C_Reputation = {
    GetNumFactions = function() return 2 end,
    GetFactionDataByIndex = function(i)
      if i == 1 then return { name = "Mock League", isHeader = true, isCollapsed = true, isHeaderWithRep = false } end
      return { name = "Mock Outriders", factionID = 9001, reaction = 5, currentReactionThreshold = 3000, nextReactionThreshold = 9000, currentStanding = 4200 }
    end,
    ExpandAllFactionHeaders = function() end,
    CollapseFactionHeader = function() end,
  }
  C_QuestLog = {
    GetNumQuestLogEntries = function() return 2 end,
    GetInfo = function(i)
      if i == 1 then return { title = "Zone", isHeader = true } end
      return { title = "Mock Quest", level = 35, questID = 990001 }
    end,
    IsComplete = function() return false end,
    GetAllCompletedQuestIDs = function() return completed end,
  }
  C_Container = {
    GetContainerNumSlots = function(bag) if loggedOut then return 0 end return (bag == 0 or bag == -1) and 3 or 0 end,
    GetContainerItemInfo = function(bag, slot)
      if slot == 1 then return { itemID = 920001, stackCount = 20 } end
      if slot == 2 then return { itemID = 920001, stackCount = 5 } end
      return nil
    end,
  }
  local tradeCalls = 0
  C_TradeSkillUI = {
    GetBaseProfessionInfo = function() return { professionName = "Tailoring", skillLevel = 100, maxSkillLevel = 150, professionID = 165 } end,
    GetChildProfessionInfo = function() return { professionName = "Tailoring", skillLevel = 100, maxSkillLevel = 150 } end,
    -- the first call comes back empty (data not loaded yet): the add-on must try again
    GetAllRecipeIDs = function() tradeCalls = tradeCalls + 1; if tradeCalls == 1 then return {} end return { 930001, 930002, 930003 } end,
    GetFilteredRecipeIDs = function() return {} end,
    GetRecipeInfo = function(id)
      if id == 930001 then return { name = "Mock Bolt of Silk", learned = true, relativeDifficulty = 2, numSkillUps = 1 } end
      if id == 930002 then return { name = "Mock Belt", learned = true, relativeDifficulty = 0, numSkillUps = 1 } end
      return { name = "Mock Silk Cap", learned = false }
    end,
    GetRecipeSchematic = function(id)
      return { outputItemID = id == 930001 and 920005 or 920006, reagentSlotSchematics = {
        { reagents = { { itemID = 920007 } }, quantityRequired = 1 }, { reagents = { { itemID = 920001 } }, quantityRequired = 1 } } }
    end,
    GetRecipeSourceText = function() return "|cFFFFD200Source:|r Drop: Mock Boss" end,
  }
  C_ClassTalents = { GetActiveConfigID = function() if loggedOut then return nil end return 7 end }
  C_Traits = {
    GetConfigInfo = function() return { treeIDs = { 1 } } end,
    GetTreeNodes = function() return { 10, 11 } end,
    GetNodeInfo = function(_, node)
      if node == 10 then return { currentRank = 3, maxRanks = 5, activeEntry = { entryID = 100 } } end
      return { currentRank = 0, maxRanks = 1 }
    end,
    GetEntryInfo = function() return { definitionID = 200 } end,
    GetDefinitionInfo = function() return { spellID = 930010 } end,
  }
elseif variant == "legacy" then
  local shut = true
  function GetNumSkillLines() if loggedOut then return 0 end return shut and 2 or 4 end
  function GetSkillLineInfo(i)
    if shut then
      if i == 1 then return "Professions", true, false end
      return "Weapon Skills", true, false
    end
    if i == 1 then return "Professions", true, true end
    if i == 2 then return "Tailoring", false, nil, 100, 0, 0, 150 end
    if i == 3 then return "Weapon Skills", true, true end
    return "Bows", false, nil, 120, 0, 0, 125
  end
  function ExpandSkillHeader() shut = false end
  function CollapseSkillHeader() shut = true end
  function GetNumFactions() return 2 end
  function GetFactionInfo(i)
    if i == 1 then return "Mock League", "", 0, 0, 0, 0, false, false, true, true, false, false, false, 0 end
    return "Mock Outriders", "", 5, 3000, 9000, 4200, false, false, false, false, true, false, false, 9001
  end
  function GetNumQuestLogEntries() return 2 end
  function GetQuestLogTitle(i)
    if i == 1 then return "Zone", 0, nil, true end
    return "Mock Quest", 35, nil, false, false, false, nil, 990001
  end
  function GetQuestsCompleted()
    local t = {}
    for _, id in ipairs(completed) do t[id] = true end
    t[999999] = false
    return t
  end
  function GetNumTalentTabs() if loggedOut then return 0 end return 3 end
  function GetTalentTabInfo(t) return ({ "Tree One", "Tree Two", "Tree Three" })[t], "icon", t == 2 and 11 or 0 end
  function GetNumTalents() return 2 end
  function GetTalentInfo(t, i) if t == 2 then return "Mock Shot", "icon", 1, i, i == 1 and 1 or 0, 1 end return "None", "icon", 1, i, 0, 1 end
  function GetContainerNumSlots(bag) if loggedOut then return 0 end return (bag == 0 or bag == -1) and 2 or 0 end
  function GetContainerItemInfo(_, slot) if slot == 1 then return "tex", 20, false, 1, false, false, link(920001, "Mock Salt", "ffffffff") end end
  function GetNumTradeSkills() return 3 end
  function GetTradeSkillLine() return "Tailoring", 100, 150 end
  function GetTradeSkillInfo(i) if i == 1 then return "Leather", "header" end return i == 2 and "Mock Bolt of Silk" or "Mock Belt", i == 2 and "easy" or "optimal", 5 end
  function GetTradeSkillItemLink(i) return link(i == 2 and 920005 or 920006, "x", "ffffffff") end
  function GetNumTradeSkillReagents() return 2 end
  function GetTradeSkillReagentInfo(_, j) return "r", "t", 1, 5 end
  function GetTradeSkillReagentItemLink(_, j) return link(j == 1 and 920007 or 920001, "r", "ffffffff") end
end

-- load the add-on and play a session
-- from here on every global the add-on assigns is recorded: it may create its own two and nothing else
-- (SlashCmdList is the game's: the add-on may add a field to it, never assign it)
local written, slash = {}, SlashCmdList
rawset(_G, "SlashCmdList", nil)
setmetatable(_G, {
  __index = function(_, k) if k == "SlashCmdList" then return slash end end,
  __newindex = function(t, k, v) written[#written + 1] = tostring(k); rawset(t, k, v) end,
})
local chunk = assert(loadfile(dir .. "/ForeverBridge.lua"))
chunk("ForeverBridge", {})
local f = frames[1]
local function fire(event, a) f.scripts.OnEvent(f, event, a) end
fireEvent = fire
local function check(cond, what)
  if not cond then error("CHECK FAILED (" .. variant .. "): " .. what) end
end
fire("ADDON_LOADED", "SomeOtherAddon")
fire("ADDON_LOADED", "ForeverBridge")
fire("PLAYER_LOGIN")
fire("PLAYER_EQUIPMENT_CHANGED")
fire("TRADE_SKILL_SHOW")
fire("TRAINER_SHOW")
fire("PLAYER_INTERACTION_MANAGER_FRAME_SHOW", 7)
fire("PLAYER_INTERACTION_MANAGER_FRAME_SHOW", 5)
fire("TRAINER_CLOSED")
fire("MERCHANT_SHOW")
npcGone = true
fire("MERCHANT_SHOW") -- the same window with a player targeted: nothing of that player may be stored
fire("TRAINER_SHOW")
npcGone = false
fire("BANKFRAME_OPENED")
check(SlashCmdList.FOREVERBRIDGE ~= nil and SLASH_FOREVERBRIDGE1 == "/fbridge", "the /fbridge command")
SlashCmdList.FOREVERBRIDGE("")
SlashCmdList.FOREVERBRIDGE("diag")
SlashCmdList.FOREVERBRIDGE("save")
if variant ~= "minimal" then
  check(reloaded, "/fbridge save reloaded the UI")
  SlashCmdList.FOREVERBRIDGE("auto on")
  check(ForeverBridgeDB.auto == true, "auto on")
  clock = clock + 21 * 60 -- the session has run longer than the 20 minutes auto-save waits for
  resting = true
  for _, case in ipairs({ { true, false, false, false, false, "casting" }, { false, true, false, false, false, "channelling" },
                          { false, false, true, false, false, "a popup is open" },
                          { false, false, false, true, false, "a ready check is open" },
                          { false, false, false, false, true, "a loot roll is open" } }) do
    autoBlockers(case[1], case[2], case[3], case[4], case[5])
    reloaded = false
    fire("PLAYER_EQUIPMENT_CHANGED")
    tickers[1]()
    check(not reloaded, "no auto-save while " .. case[6])
  end
  autoBlockers(false, false, false, false, false)
  reloaded = false
  resting = true
  fire("PLAYER_EQUIPMENT_CHANGED")
  tickers[1]()
  check(reloaded, "auto-save reloads when everything is quiet")
  reloaded = false
  resting = false
  fire("PLAYER_EQUIPMENT_CHANGED")
  tickers[1]()
  check(not reloaded, "no auto-save when not resting")
  resting, combat = true, true
  fire("PLAYER_EQUIPMENT_CHANGED")
  tickers[1]()
  check(not reloaded, "no auto-save in combat")
  combat = false
  SlashCmdList.FOREVERBRIDGE("auto off")
  check(ForeverBridgeDB.auto == false, "auto off")
  fire("PLAYER_EQUIPMENT_CHANGED")
  tickers[1]()
  check(not reloaded, "auto off means no reload")
  SlashCmdList.FOREVERBRIDGE("stop")
  -- a trainer window that refreshes whenever a filter changes: the add-on reads it once, not in a loop
  queueTimers, trainerOpen, trainerReads, filterFlips = true, true, 0, 0
  fire("TRAINER_SHOW")
  local steps = 0
  while #queued > 0 and steps < 200 do
    table.remove(queued, 1)()
    steps = steps + 1
  end
  check(#queued == 0, "the trainer list is not read again and again while the window stays open")
  check(trainerReads == 1 and filterFlips <= 4, "one read and its filter changes (reads " .. trainerReads ..
    ", filter changes " .. filterFlips .. ")")
  trainerOpen = false
  fire("TRAINER_CLOSED")
  local fullNote = ForeverBridgeDB.notes and ForeverBridgeDB.notes.trainer -- what the full list's read noted
  -- a window whose list stays empty: three reads at most, then the add-on stops, whatever comes back
  trainerEmpty, trainerOpen, trainerReads, filterFlips = true, true, 0, 0
  fire("TRAINER_SHOW")
  steps = 0
  while #queued > 0 and steps < 200 do
    table.remove(queued, 1)()
    steps = steps + 1
  end
  check(#queued == 0 and trainerReads <= 3, "an empty trainer list is read at most three times (reads " ..
    trainerReads .. ", filter changes " .. filterFlips .. ")")
  check(filterFlips <= 12, "a bounded number of filter changes for an empty list (" .. filterFlips .. ")")
  check(ForeverBridgeDB.notes.trainer.count == 0 and ForeverBridgeDB.notes.trainer.listed == 0, "the empty read is noted")
  -- the next window starts afresh: it gets its own three reads (the count is cleared when a window opens or closes)
  trainerOpen = false
  fire("TRAINER_CLOSED")
  trainerOpen, trainerReads = true, 0
  fire("TRAINER_SHOW")
  steps = 0
  while #queued > 0 and steps < 200 do
    table.remove(queued, 1)()
    steps = steps + 1
  end
  check(trainerReads == 3, "a second window gets its three reads again (reads " .. trainerReads .. ")")
  ForeverBridgeDB.notes.trainer = fullNote -- the checks below look at the full list's note
  trainerEmpty, trainerOpen = false, false
  fire("TRAINER_CLOSED")
  queueTimers = false
  -- logout: the real client has already emptied the inventory, bags, quest history, professions and talents
  loggedOut = true
  worn = {}
  completed = {}
end
fire("PLAYER_LOGOUT")

-- write ForeverBridgeDB out the way the game writes a SavedVariables file: ["key"] = value, an array's items
-- first with "-- [n]" after each, then the other keys, numbers before strings, each group in order
local function quoted(text)
  local escapes = { ["\\"] = "\\\\", ['"'] = '\\"', ["\n"] = "\\n", ["\r"] = "\\r" }
  return '"' .. text:gsub('[\\"\n\r]', escapes) .. '"'
end
local function number(value)
  local whole = math.floor(value)
  if whole == value and whole > -1e15 and whole < 1e15 then return string.format("%d", value) end
  return string.format("%.14g", value)
end
local function ordered(tbl, count)
  local numbers, names = {}, {}
  for k in pairs(tbl) do
    local inArray = type(k) == "number" and k >= 1 and k <= count and math.floor(k) == k
    if not inArray then
      if type(k) == "number" then numbers[#numbers + 1] = k else names[#names + 1] = k end
    end
  end
  table.sort(numbers)
  table.sort(names)
  for _, k in ipairs(names) do numbers[#numbers + 1] = k end
  return numbers
end
local lines = {}
local function emit(value, label, ending)
  local kind = type(value)
  if kind == "table" then
    lines[#lines + 1] = label .. "{"
    local count = #value
    for i = 1, count do emit(value[i], "", ", -- [" .. i .. "]") end
    for _, k in ipairs(ordered(value, count)) do
      local key = type(k) == "number" and ("[" .. number(k) .. "] = ") or ("[" .. quoted(k) .. "] = ")
      emit(value[k], key, ",")
    end
    lines[#lines + 1] = "}" .. ending
  elseif kind == "string" then
    lines[#lines + 1] = label .. quoted(value) .. ending
  elseif kind == "number" then
    lines[#lines + 1] = label .. number(value) .. ending
  elseif kind == "boolean" then
    lines[#lines + 1] = label .. tostring(value) .. ending
  end
end
lines[#lines + 1] = "ForeverBridgeDB = {"
for _, k in ipairs(ordered(ForeverBridgeDB, 0)) do emit(ForeverBridgeDB[k], "[" .. quoted(k) .. "] = ", ",") end
lines[#lines + 1] = "}"
local fh = assert(io.open(outfile, "w"))
fh:write(table.concat(lines, "\n"), "\n")
fh:close()

-- checks
local rec = ForeverBridgeDB.chars["Testa-Mockrealm"]
check(rec, "the character record exists")
if variant == "modern" then
  check(ForeverBridgeDB.chars["Testa-"] == nil, "the older Testa- record moved")
  check(rec.stale == true, "its data moved to Testa-Mockrealm")
end
if variant ~= "minimal" then
  check(rec.reason == "logout", "the last snapshot is the logout one")
  check(rec.level == 22 and rec.class == "WARLOCK" and rec.race == "Undead", "identity")
  check(rec.xp == 12000 and rec.xpMax == 27300 and rec.money == 123456, "experience and money kept at logout")
  check(#rec.equipped == 5 and rec.equipped[1].slot == "Head" and rec.equipped[1].id == 900001, "equipped items kept at logout")
  check(rec.equipped[1].stats and rec.equipped[1].stats.ITEM_MOD_AGILITY_SHORT == 8, "item stats")
  for _, e in ipairs(rec.equipped) do
    check(e.tip == nil, "no tooltip lines stored for a worn item (they can name other players)")
  end
  check(rec.equipped[1].name == "Mock Silk Cap" and rec.equipped[1].item == nil, "item name, and no item string")
  check(rec.stats.agility == 24 and rec.stats.stamina == 36 and rec.stats.attackPower == 120 and rec.stats.ranged.speed == 2.4, "stats kept at logout")
  check(rec.position.x == 63.1 and rec.position.y == 44.9 and rec.position.map == 9901, "position kept at logout (same zone)")
  check(rec.pet and rec.pet.name == "Mockpet", "pet kept at logout")
  local salt = (variant == "modern") and 25 or 20
  check(rec.bags[920001] == salt, "bags kept at logout: " .. salt .. " (got " .. tostring(rec.bags[920001]) .. ")")
  check(rec.bank and rec.bank[920001] == salt, "bank")
  check(#rec.reputation == 1 and rec.reputation[1].name == "Mock Outriders" and rec.reputation[1].value == 4200, "reputation")
  check(#rec.quests.completed == 3, "completed quests kept at logout (got " .. #rec.quests.completed .. ")")
  check(#rec.quests.active == 1 and rec.quests.active[1].id == 990001, "active quests")
  local kept = table.concat(rec.kept or {}, ",")
  check(kept:find("equipped") and kept:find("bags") and kept:find("quests.completed") and kept:find("pet")
    and kept:find("xpMax") and kept:find("money") and kept:find("stats"), "kept parts listed: " .. kept)
  local ts = rec.tradeskills.Tailoring
  check(ts and #ts.recipes >= 2 and ts.rank == 100, "trade skill recipes")
  check(ts.recipes[1].reagents[1][1] == 920007 and ts.recipes[1].reagents[2][2] == 1, "recipe reagents")
  local trainer = ForeverBridgeDB.trainers["980001"]
  check(trainer and #trainer.services == 2 and trainer.services[1].reqRank == 75 and trainer.services[1].cost == 100 and trainer.services[1].spell == 930001, "trainer")
  local vendor = ForeverBridgeDB.vendors["980001"]
  check(vendor and #vendor.items == 2 and vendor.items[1].price == 350 and vendor.items[2].limited == 1, "vendor")
  check(ForeverBridgeDB.diag and ForeverBridgeDB.diag.has.GetProfessions ~= nil, "diag")
  local nv, nt = 0, 0
  for _ in pairs(ForeverBridgeDB.vendors) do nv = nv + 1 end
  for _ in pairs(ForeverBridgeDB.trainers) do nt = nt + 1 end
  check(nv == 1 and nt == 1, "only the creature's vendor and trainer lists are stored")
  for key, v in pairs(ForeverBridgeDB.vendors) do
    check(v.name ~= "Otherplayer" and key ~= "Otherplayer", "no other player stored as a vendor")
  end
  for key, t in pairs(ForeverBridgeDB.trainers) do
    check(t.name ~= "Otherplayer" and key ~= "Otherplayer", "no other player stored as a trainer")
  end
  local saved = assert(io.open(outfile)):read("*a")
  check(not saved:find("Otherplayer", 1, true), "no other player's name anywhere in the saved file")
  check(not saved:find("Player-", 1, true), "no player id (a crafter's) anywhere in the saved file")
  if variant == "modern" then
    check(trainerFilters.available == true and trainerFilters.unavailable == false and trainerFilters.used == false,
      "the trainer window's filters are put back as the player had them (true and false)")
  else
    check(trainerFilters.available == 1 and trainerFilters.unavailable == nil and trainerFilters.used == nil,
      "the trainer window's filters are put back as the player had them")
  end
  local notes = ForeverBridgeDB.notes
  check(notes and notes.trainer and notes.trainer.count == 3 and notes.trainer.listed == 2 and #notes.trainer.sample >= 2, "trainer notes")
  check(ForeverBridgeDB.events and ForeverBridgeDB.events.TRAINER_SHOW and ForeverBridgeDB.events.TRAINER_SHOW.n == 5, "event counts")
  check(ForeverBridgeDB.events.PLAYER_INTERACTION_MANAGER_FRAME_SHOW.n == 2, "interaction events counted")
  check(ForeverBridgeDB.diag.globals and #ForeverBridgeDB.diag.globals.namespaces > 0, "diag globals")
  check(rec.errors == nil, "no errors recorded: " .. tostring(rec.errors and (next(rec.errors))))
  for _, p in ipairs(printed) do
    check(p:find("ForeverBridge", 1, true), "every chat line names the add-on: " .. p)
  end
  if variant == "modern" then
    check(notes.tradeskill and notes.tradeskill.tries == 1 and notes.tradeskill.event == "retry" and notes.tradeskill.recipes == 3, "trade skill retried after an empty first answer")
    check(#rec.skills.professions == 2 and rec.skills.professions[1].name == "Tailoring" and rec.skills.professions[1].rank == 100, "professions kept at logout")
    check(rec.talents.tabs[1] and rec.talents.tabs[1].talents[1].spell == 930010, "talents (traits) kept at logout")
    check(ts.recipes[1].diff == 2 and ts.recipes[2].diff == 0 and ts.recipes[3].src == "Source: Drop: Mock Boss", "recipe colours and source")
    -- a logout in ANOTHER zone must not keep the old x, y
    zoneName = "Otherzone"
    fire("PLAYER_LOGOUT")
    check(rec.position.zone == "Otherzone" and rec.position.x == nil, "no old x, y in a new zone")
    check(#rec.equipped == 5, "gear still kept on a second logout")
  else
    check(#rec.skills.lines == 2 and rec.skills.lines[1].name == "Tailoring" and rec.skills.lines[1].rank == 100, "skill lines kept at logout")
    check(rec.skills.lines[2].group == "Weapon Skills", "skill line groups")
    check(rec.talents.tabs[2].points == 11 and rec.talents.tabs[2].talents[1].name == "Mock Shot", "legacy talents kept at logout")
    check(ts.recipes[1].diff == 2 and ts.recipes[2].diff == 0, "legacy recipe colours")
  end
end
for _, k in ipairs(written) do
  check(k == "SLASH_FOREVERBRIDGE1" or k == "ForeverBridgeDB", "the add-on assigned the global " .. k)
end
io.stdout:write("OK ", variant, " lines=", #lines, " printed=", #printed, "\n")
for _, p in ipairs(printed) do io.stdout:write("  chat: ", p, "\n") end
