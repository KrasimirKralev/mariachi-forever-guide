-- ForeverBridge: a snapshot of YOUR OWN character, kept in one local file for the Forever Guide on your PC.
--
--   * WoW writes WTF/Account/<account>/SavedVariables/ForeverBridge.lua on /reload and on logout; the
--     `forever` command line reads that file. The add-on sends nothing anywhere (WoW add-ons cannot reach the internet).
--   * Recorded: the character (level, class, XP, money, place), worn items, stats, skills and
--     professions, reputation, quests, talents, pet, bags (and the bank once it is opened), recipes
--     (when a profession window is opened) and what trainers and vendors list (when their window is
--     opened). NOT recorded: chat, whispers, guild notes, friends, other players.
--   * Every part runs inside pcall: a function this client does not have is noted in the data
--     (errors, diag) and never raises an error in the game.
--   * The snapshot taken while logging out sees a half-dismantled character (0 experience, 0 money, no gear, no
--     bags, no quest history ...), so in that one snapshot a blank answer keeps the value read before it.
--
--   /fbridge           says how old the snapshot is
--   /fbridge save      refreshes it and reloads the UI, so that the file is written now
--   /fbridge auto on   opt-in: reload by itself while resting in a town (auto off, stop)
--   /fbridge diag      says which game functions this client has

local ADDON_NAME = ...
local SCHEMA = 1
local VERSION = "1.1"

local DB
local frame = CreateFrame("Frame")
local lastSnapshot = 0

-- helpers ----------------------------------------------------------------------------------------

-- Game functions differ between clients, and any of them may be missing or fail. safeCall runs one when it
-- exists and hands back what it returned, or nothing when it is missing or raised an error.
local function passResults(ok, ...)
  if ok then return ... end
end

local function safeCall(fn, ...)
  if type(fn) == "function" then
    return passResults(pcall(fn, ...))
  end
end

-- only the first value a call returns
local function firstOf(fn, ...)
  local value = safeCall(fn, ...)
  return value
end

local function nowTime()
  if type(time) == "function" then return time() end
  return firstOf(GetServerTime) or 0
end

local function plain(s)
  if type(s) ~= "string" then return s end
  s = string.gsub(s, "|c%x%x%x%x%x%x%x%x", "")
  s = string.gsub(s, "|r", "")
  s = string.gsub(s, "|T.-|t", "")
  return s
end

local function say(text)
  print("|cff7fd0ffForeverBridge|r " .. text)
end

local function itemIdOf(link)
  if type(link) ~= "string" then return nil end
  return tonumber(string.match(link, "item:(%-?%d+)"))
end

local function itemNameOf(link)
  if type(link) ~= "string" then return nil end
  return string.match(link, "%[(.-)%]")
end

local function itemInfo(link)
  local fn = _G.GetItemInfo
  if type(fn) ~= "function" and _G.C_Item then fn = _G.C_Item.GetItemInfo end
  return safeCall(fn, link)
end

-- this client's GetRealmName() can be empty: ask the full name first
local function realmName()
  local _, realm = safeCall(UnitFullName, "player")
  if type(realm) == "string" and realm ~= "" then return realm end
  realm = firstOf(GetRealmName)
  if type(realm) == "string" and realm ~= "" then return realm end
  realm = firstOf(GetNormalizedRealmName)
  if type(realm) == "string" and realm ~= "" then return realm end
  return ""
end

-- a map position as the game's coordinates show it: per cent with one decimal
local function oneDecimal(fraction)
  return tonumber(string.format("%.1f", fraction))
end

-- what each window collector saw, so that a silent failure can be understood from the data
local function scalars(t)
  local out, n = {}, 0
  if type(t) ~= "table" then return out end
  for k, v in pairs(t) do
    local kind = type(v)
    if kind == "string" or kind == "number" or kind == "boolean" then
      out[tostring(k)] = v
      n = n + 1
      if n >= 40 then break end
    end
  end
  return out
end

local function rawlist(fn, ...)
  local words = {}
  local function collect(...)
    for i = 1, select("#", ...) do words[i] = tostring((select(i, ...))) end
  end
  collect(safeCall(fn, ...))
  return table.concat(words, " | ")
end

-- the character ----------------------------------------------------------------------------------

local function collectIdentity()
  local t = {}
  t.name = firstOf(UnitName, "player")
  t.realm = realmName()
  t.level = firstOf(UnitLevel, "player")
  local className, classFile = safeCall(UnitClass, "player")
  t.class, t.classLocal = classFile, className
  local raceName, raceFile = safeCall(UnitRace, "player")
  t.race, t.raceFile = raceName, raceFile
  t.faction = firstOf(UnitFactionGroup, "player")
  t.sex = firstOf(UnitSex, "player")
  t.xp = firstOf(UnitXP, "player")
  t.xpMax = firstOf(UnitXPMax, "player")
  t.rested = firstOf(GetXPExhaustion)
  t.money = firstOf(GetMoney)
  local version, build, date, toc = safeCall(GetBuildInfo)
  t.game = { version = version, build = build, toc = toc }
  return t
end

local SLOTS = { [0] = "Ammo", "Head", "Neck", "Shoulder", "Shirt", "Chest", "Waist", "Legs", "Feet", "Wrist",
  "Hands", "Finger1", "Finger2", "Trinket1", "Trinket2", "Back", "MainHand", "OffHand", "Ranged", "Tabard" }

local function collectEquipped()
  local out = {}
  for slot = 0, 19 do
    local link = firstOf(GetInventoryItemLink, "player", slot)
    if link then
      -- the id and the name only: the rest of a link can carry the id of the player who made the item
      local e = { slot = SLOTS[slot], index = slot, id = itemIdOf(link), name = itemNameOf(link) }
      local enchant = tonumber(string.match(link, "item:%-?%d+:(%-?%d+)") or "")
      if enchant and enchant > 0 then e.enchant = enchant end
      local cur, max = safeCall(GetInventoryItemDurability, slot)
      if cur then e.dur, e.durMax = cur, max end
      local count = firstOf(GetInventoryItemCount, "player", slot)
      if count and count > 1 then e.count = count end
      local _, _, quality, ilvl = itemInfo(link)
      e.quality, e.ilvl = quality, ilvl
      -- the real numbers of this very item, random suffix included
      local statsFn = _G.GetItemStats or (_G.C_Item and C_Item.GetItemStats)
      local stats = safeCall(statsFn, link)
      if type(stats) == "table" then e.stats = scalars(stats) end
      -- no tooltip text is kept: a crafted or gifted item's tooltip names the player who made or gave it, in
      -- the client's own language, and nothing here reads it
      out[#out + 1] = e
    end
  end
  return out
end

local function collectStats()
  local s = {}
  local names = { "strength", "agility", "stamina", "intellect", "spirit" }
  for i = 1, 5 do
    local base, effective = safeCall(UnitStat, "player", i)
    s[names[i]] = effective or base
  end
  local baseArmor, effectiveArmor = safeCall(UnitArmor, "player")
  s.armor = effectiveArmor or baseArmor
  local function power(fn)
    local base, plus, minus = safeCall(fn, "player")
    if base then return base + (plus or 0) + (minus or 0) end
  end
  s.attackPower = power(UnitAttackPower)
  s.rangedAttackPower = power(UnitRangedAttackPower)
  s.meleeCrit = firstOf(GetCritChance)
  s.rangedCrit = firstOf(GetRangedCritChance)
  s.dodge = firstOf(GetDodgeChance)
  s.parry = firstOf(GetParryChance)
  s.block = firstOf(GetBlockChance)
  local speed, low, high = safeCall(UnitRangedDamage, "player")
  if speed then s.ranged = { speed = speed, min = low, max = high } end
  s.meleeSpeed = firstOf(UnitAttackSpeed, "player")
  s.health = firstOf(UnitHealthMax, "player")
  s.mana = firstOf(UnitPowerMax, "player", 0)
  return s
end

local function collectPosition()
  local p = { zone = firstOf(GetZoneText), sub = firstOf(GetSubZoneText) }
  if p.zone == "" then p.zone = nil end
  if p.sub == "" then p.sub = nil end
  local M = _G.C_Map
  if M and M.GetBestMapForUnit then
    local map = firstOf(M.GetBestMapForUnit, "player")
    if map then
      p.map = map
      local pos = M.GetPlayerMapPosition and firstOf(M.GetPlayerMapPosition, map, "player")
      if pos then
        local x, y = safeCall(pos.GetXY, pos)
        if x and y then p.x, p.y = oneDecimal(x * 100), oneDecimal(y * 100) end
      end
    end
  end
  return p
end

-- skills and professions ------------------------------------------------------------------------

local function collectSkills()
  local out = { lines = {}, professions = {} }
  -- the older skills list: expand every header to see all lines, then put the headers back
  local count = firstOf(GetNumSkillLines)
  if count then
    local shut = {}
    for i = 1, count do
      local name, header, expanded = safeCall(GetSkillLineInfo, i)
      if header and not expanded then shut[name] = true end
    end
    if next(shut) then safeCall(ExpandSkillHeader, 0) end
    count = firstOf(GetNumSkillLines) or count
    local group
    for i = 1, count do
      local name, header, _, rank, _, modifier, maxRank = safeCall(GetSkillLineInfo, i)
      if name then
        if header then
          group = name
        else
          out.lines[#out.lines + 1] = { name = name, rank = rank, max = maxRank, group = group,
            plus = (modifier and modifier ~= 0) and modifier or nil }
        end
      end
    end
    if next(shut) then
      for i = count, 1, -1 do
        local name, header = safeCall(GetSkillLineInfo, i)
        if header and shut[name] then safeCall(CollapseSkillHeader, i) end
      end
    end
  end
  -- the newer professions list
  if type(GetProfessions) == "function" then
    local p = { safeCall(GetProfessions) }
    for i = 1, 6 do
      local index = p[i]
      if index then
        local name, _, rank, maxRank, _, _, skillLine = safeCall(GetProfessionInfo, index)
        if name then
          out.professions[#out.professions + 1] = { name = name, rank = rank, max = maxRank, skillLine = skillLine, slot = i }
        end
      end
    end
  end
  return out
end

-- reputation ------------------------------------------------------------------------------------

local function collectReputation()
  local out = {}
  local R = _G.C_Reputation
  if R and R.GetNumFactions and R.GetFactionDataByIndex then
    local shut = {}
    for i = 1, (firstOf(R.GetNumFactions) or 0) do
      local d = firstOf(R.GetFactionDataByIndex, i)
      if type(d) == "table" and d.isHeader and d.isCollapsed then shut[d.name] = true end
    end
    if next(shut) then safeCall(R.ExpandAllFactionHeaders) end
    local count = firstOf(R.GetNumFactions) or 0
    for i = 1, count do
      local d = firstOf(R.GetFactionDataByIndex, i)
      if type(d) == "table" and d.name and (not d.isHeader or d.isHeaderWithRep) then
        out[#out + 1] = { name = d.name, id = d.factionID, standing = d.reaction, min = d.currentReactionThreshold,
          max = d.nextReactionThreshold, value = d.currentStanding }
      end
    end
    if next(shut) then
      for i = count, 1, -1 do
        local d = firstOf(R.GetFactionDataByIndex, i)
        if type(d) == "table" and d.isHeader and shut[d.name] then safeCall(R.CollapseFactionHeader, i) end
      end
    end
  elseif type(GetNumFactions) == "function" then
    local shut = {}
    for i = 1, (firstOf(GetNumFactions) or 0) do
      local name, _, _, _, _, _, _, _, header, collapsed = safeCall(GetFactionInfo, i)
      if header and collapsed then shut[name] = true end
    end
    if next(shut) then safeCall(ExpandAllFactionHeaders) end
    local count = firstOf(GetNumFactions) or 0
    for i = 1, count do
      local name, _, standing, low, high, value, _, _, header, _, hasRep, _, _, id = safeCall(GetFactionInfo, i)
      if name and (not header or hasRep) then
        out[#out + 1] = { name = name, id = id, standing = standing, min = low, max = high, value = value }
      end
    end
    if next(shut) then
      for i = count, 1, -1 do
        local name, _, _, _, _, _, _, _, header = safeCall(GetFactionInfo, i)
        if header and shut[name] then safeCall(CollapseFactionHeader, i) end
      end
    end
  end
  return out
end

-- quests ----------------------------------------------------------------------------------------

local function collectQuests()
  local out = { active = {}, completed = {} }
  local Q = _G.C_QuestLog
  if Q and Q.GetNumQuestLogEntries and Q.GetInfo then
    for i = 1, (firstOf(Q.GetNumQuestLogEntries) or 0) do
      local info = firstOf(Q.GetInfo, i)
      if type(info) == "table" and not info.isHeader and info.questID then
        out.active[#out.active + 1] = { id = info.questID, title = info.title, level = info.level,
          complete = Q.IsComplete and firstOf(Q.IsComplete, info.questID) or nil }
      end
    end
  elseif type(GetNumQuestLogEntries) == "function" then
    for i = 1, (firstOf(GetNumQuestLogEntries) or 0) do
      local title, level, _, header, _, complete, _, id = safeCall(GetQuestLogTitle, i)
      if title and not header then
        out.active[#out.active + 1] = { id = id, title = title, level = level, complete = complete and true or nil }
      end
    end
  end
  local list = Q and Q.GetAllCompletedQuestIDs and firstOf(Q.GetAllCompletedQuestIDs)
  if type(list) == "table" then
    for _, id in ipairs(list) do out.completed[#out.completed + 1] = id end
  elseif type(GetQuestsCompleted) == "function" then
    local all = firstOf(GetQuestsCompleted)
    if type(all) == "table" then
      for id, done in pairs(all) do
        if done then out.completed[#out.completed + 1] = id end
      end
    end
  end
  table.sort(out.completed)
  return out
end

-- talents, pet, bags ----------------------------------------------------------------------------

local function collectTalents()
  local out = { tabs = {} }
  if type(GetNumTalentTabs) == "function" and type(GetTalentInfo) == "function" then
    for tab = 1, (firstOf(GetNumTalentTabs) or 0) do
      local tabName, _, spent = safeCall(GetTalentTabInfo, tab)
      local t = { name = tabName, points = spent, talents = {} }
      for i = 1, (firstOf(GetNumTalents, tab) or 0) do
        local answer = { safeCall(GetTalentInfo, tab, i) } -- name, icon, tier, column, rank, max rank
        local spent = answer[5]
        if answer[1] and spent and spent > 0 then
          t.talents[#t.talents + 1] = { name = answer[1], tier = answer[3], col = answer[4], rank = spent, max = answer[6] }
        end
      end
      out.tabs[#out.tabs + 1] = t
    end
  end
  if #out.tabs == 0 and _G.C_ClassTalents and _G.C_Traits then
    -- the traits system: the spent nodes, as spell ids (names are looked up on the PC)
    local t = { name = "traits", talents = {} }
    pcall(function()
      local configID = firstOf(C_ClassTalents.GetActiveConfigID)
      local config = configID and firstOf(C_Traits.GetConfigInfo, configID)
      for _, treeID in ipairs((config and config.treeIDs) or {}) do
        for _, nodeID in ipairs(firstOf(C_Traits.GetTreeNodes, treeID) or {}) do
          local node = firstOf(C_Traits.GetNodeInfo, configID, nodeID)
          if type(node) == "table" and node.currentRank and node.currentRank > 0 then
            local entryID = node.activeEntry and node.activeEntry.entryID
            local entry = entryID and firstOf(C_Traits.GetEntryInfo, configID, entryID)
            local def = entry and entry.definitionID and firstOf(C_Traits.GetDefinitionInfo, entry.definitionID)
            t.talents[#t.talents + 1] = { node = nodeID, rank = node.currentRank, max = node.maxRanks, spell = def and def.spellID }
          end
        end
      end
    end)
    if #t.talents > 0 then out.tabs[1] = t end
  end
  return out
end

local function collectPet()
  if not firstOf(UnitExists, "pet") then return nil end
  return { name = firstOf(UnitName, "pet"), level = firstOf(UnitLevel, "pet"), family = firstOf(UnitCreatureFamily, "pet") }
end

-- One slot of a bag: the item's id and how many there are, or nothing when the slot is empty. Newer clients
-- answer through C_Container with a table, older ones with a list of values (the link is the seventh).
local function slotContents(bag, slot)
  local api = _G.C_Container
  if api and api.GetContainerItemInfo then
    local info = firstOf(api.GetContainerItemInfo, bag, slot)
    if type(info) ~= "table" then return nil end
    return info.itemID or itemIdOf(info.hyperlink), info.stackCount or 1
  end
  local answer = { safeCall(GetContainerItemInfo, bag, slot) }
  local itemId = itemIdOf(answer[7])
  if itemId then return itemId, answer[2] or 1 end
end

local function slotTotal(bag)
  local api = _G.C_Container
  local getter = (api and api.GetContainerNumSlots) or _G.GetContainerNumSlots
  return firstOf(getter, bag) or 0
end

-- how many of each item the given bags hold, keyed by item id
local function countItems(bagList)
  local tally = {}
  for _, bag in ipairs(bagList) do
    for slot = 1, slotTotal(bag) do
      local itemId, howMany = slotContents(bag, slot)
      if itemId then tally[itemId] = howMany + (tally[itemId] or 0) end
    end
  end
  return tally
end

local function collectBags()
  local bags = {}
  for bag = 0, (_G.NUM_BAG_SLOTS or 4) do bags[#bags + 1] = bag end
  return countItems(bags)
end

-- recipes, trainers, vendors (only when their window is open) ------------------------------------

local LEGACY_DIFFICULTY = { optimal = 0, medium = 1, easy = 2, trivial = 3 }

local function collectTradeSkill()
  local out = { recipes = {} }
  local T = _G.C_TradeSkillUI
  if T and T.GetAllRecipeIDs and T.GetRecipeInfo then
    local info = T.GetBaseProfessionInfo and firstOf(T.GetBaseProfessionInfo)
    local child = T.GetChildProfessionInfo and firstOf(T.GetChildProfessionInfo)
    if type(info) == "table" then
      out.name, out.rank, out.max, out.id = info.professionName, info.skillLevel, info.maxSkillLevel, info.professionID
    end
    if type(child) == "table" then
      if (not out.rank or out.rank == 0) and child.skillLevel and child.skillLevel > 0 then
        out.rank, out.max = child.skillLevel, child.maxSkillLevel
      end
      out.name = out.name or child.professionName
    end
    local ids = firstOf(T.GetAllRecipeIDs) or {}
    local filtered = T.GetFilteredRecipeIDs and firstOf(T.GetFilteredRecipeIDs) or {}
    if #ids == 0 then ids = filtered end
    out.sample = { ids = #ids, filtered = #filtered, base = scalars(info), child = scalars(child),
      recipe = scalars(ids[1] and firstOf(T.GetRecipeInfo, ids[1])) }
    for n, id in ipairs(ids) do
      if n > 2000 then break end
      local r = firstOf(T.GetRecipeInfo, id)
      if type(r) == "table" then
        local e = { id = id, name = r.name, learned = r.learned and true or false }
        if r.learned then
          e.diff = r.relativeDifficulty
          e.ups = r.numSkillUps
          local schematic = T.GetRecipeSchematic and firstOf(T.GetRecipeSchematic, id, false)
          if type(schematic) == "table" then
            e.out = schematic.outputItemID
            local reagents = {}
            for _, slot in ipairs(schematic.reagentSlotSchematics or {}) do
              local reagent = slot.reagents and slot.reagents[1]
              if reagent and reagent.itemID then reagents[#reagents + 1] = { reagent.itemID, slot.quantityRequired } end
            end
            e.reagents = reagents
          end
        else
          local source = T.GetRecipeSourceText and firstOf(T.GetRecipeSourceText, id)
          if source and source ~= "" then e.src = plain(source) end
        end
        out.recipes[#out.recipes + 1] = e
      end
    end
  elseif type(GetNumTradeSkills) == "function" then
    local name, rank, max = safeCall(GetTradeSkillLine)
    out.name, out.rank, out.max = name, rank, max
    for i = 1, (firstOf(GetNumTradeSkills) or 0) do
      local recipe, kind = safeCall(GetTradeSkillInfo, i)
      if recipe and kind ~= "header" then
        local e = { name = recipe, learned = true, diff = LEGACY_DIFFICULTY[kind] }
        e.out = itemIdOf(firstOf(GetTradeSkillItemLink, i))
        local reagents = {}
        for j = 1, (firstOf(GetNumTradeSkillReagents, i) or 0) do
          local _, _, needed = safeCall(GetTradeSkillReagentInfo, i, j)
          local id = itemIdOf(firstOf(GetTradeSkillReagentItemLink, i, j))
          if id then reagents[#reagents + 1] = { id, needed } end
        end
        e.reagents = reagents
        out.recipes[#out.recipes + 1] = e
      end
    end
  end
  return out
end

local TRAINER_KINDS = { "available", "unavailable", "used" }

local function readTrainer(out, info)
  safeCall(ExpandTrainerSkillLine, 0)
  local count = firstOf(GetNumTrainerServices)
  info.count = count
  for i = 1, (count or 0) do
    if i <= 4 then info.sample[#info.sample + 1] = rawlist(GetTrainerServiceInfo, i) end
    local name, sub, state = safeCall(GetTrainerServiceInfo, i)
    if name and state ~= "header" then
      local e = { name = name, sub = sub, state = state }
      e.cost = firstOf(GetTrainerServiceCost, i)
      local reqSkill, reqRank = safeCall(GetTrainerServiceSkillReq, i)
      e.reqSkill, e.reqRank = reqSkill, reqRank
      e.reqLevel = firstOf(GetTrainerServiceLevelReq, i)
      local link = firstOf(GetTrainerServiceItemLink, i)
      if type(link) == "string" then e.spell = tonumber(string.match(link, "spell:(%d+)")) end
      out[#out + 1] = e
    end
  end
end

-- the list, and what the trainer calls answered (for the notes). Every service is shown while it is read, then
-- the window's three filters are put back the way the player had set them.
local function collectTrainer()
  local out, info = {}, { sample = {} }
  if type(GetNumTrainerServices) ~= "function" then
    info.err = "no GetNumTrainerServices"
    return out, info
  end
  local before = {}
  local canRead = type(GetTrainerServiceTypeFilter) == "function"
  for _, kind in ipairs(TRAINER_KINDS) do
    if canRead then before[kind] = { firstOf(GetTrainerServiceTypeFilter, kind) } end
    safeCall(SetTrainerServiceTypeFilter, kind, 1)
  end
  local ok, err = pcall(readTrainer, out, info)
  if canRead then
    for _, kind in ipairs(TRAINER_KINDS) do
      -- the value goes back in the form the client gave it: true or false, else 1 or 0
      local was = before[kind][1]
      if type(was) == "boolean" then
        safeCall(SetTrainerServiceTypeFilter, kind, was)
      else
        safeCall(SetTrainerServiceTypeFilter, kind, was and 1 or 0)
      end
    end
  end
  if not ok then error(err, 0) end
  return out, info
end

local function collectMerchant()
  local out = {}
  local M = _G.C_MerchantFrame
  for i = 1, (firstOf(GetMerchantNumItems) or 0) do
    local e
    if M and M.GetItemInfo then
      local info = firstOf(M.GetItemInfo, i)
      if type(info) == "table" and info.name then
        e = { name = info.name, price = info.price, qty = info.stackCount }
        if info.numAvailable and info.numAvailable >= 0 then e.limited = info.numAvailable end
        if info.hasExtendedCost then e.ext = true end
      end
    else
      local name, _, price, quantity, available = safeCall(GetMerchantItemInfo, i)
      if name then
        e = { name = name, price = price, qty = quantity }
        if available and available >= 0 then e.limited = available end
        if (firstOf(GetMerchantItemCostInfo, i) or 0) > 0 then e.ext = true end
      end
    end
    if e then
      e.id = firstOf(GetMerchantItemID, i) or itemIdOf(firstOf(GetMerchantItemLink, i))
      out[#out + 1] = e
    end
  end
  return out
end

-- storing ----------------------------------------------------------------------------------------

local function init()
  if DB then return end
  ForeverBridgeDB = type(ForeverBridgeDB) == "table" and ForeverBridgeDB or {}
  DB = ForeverBridgeDB
  DB.schema = SCHEMA
  DB.chars = DB.chars or {}
  DB.trainers = DB.trainers or {}
  DB.vendors = DB.vendors or {}
end

local function charRecord()
  init()
  local name = firstOf(UnitName, "player")
  if not name or name == "" or name == "Unknown" then return nil end
  local realm = realmName()
  local key = realm ~= "" and (name .. "-" .. realm) or name
  -- a snapshot made before the realm was known sat under "Name-": move it
  local older = name .. "-"
  if key ~= older and type(DB.chars[older]) == "table" then
    if type(DB.chars[key]) ~= "table" then DB.chars[key] = DB.chars[older] end
    DB.chars[older] = nil
  end
  local rec = DB.chars[key]
  if type(rec) ~= "table" then
    rec = {}
    DB.chars[key] = rec
  end
  return rec, key
end

-- nil, or a table without a single entry
local function holdsNothing(value)
  if type(value) ~= "table" then return value == nil end
  for _ in pairs(value) do return false end
  return true
end

-- Seen in real saved files: while the player logs out, the client is already taking the character apart. The
-- logout snapshot then reads experience 0, money 0, stamina 0, and finds no worn items, bags, finished quests,
-- professions or talents. None of that is true, so in that snapshot a blank part keeps the value from the last
-- snapshot, and so does a blank piece inside a part (quests.completed, talents.tabs, skills.professions, ...).
-- A position counts as one piece, and only in the zone it came from: an old x, y is never put into a new zone.
local LOGOUT_ZERO = { xp = true, xpMax = true, money = true }

local function keepAtLogout(name, old, new, kept)
  if holdsNothing(old) then return new end
  if holdsNothing(new) then
    kept[#kept + 1] = name
    return old
  end
  if type(old) ~= "table" or type(new) ~= "table" then return new end
  if name == "stats" then
    -- stamina is never 0 on a character in the world: a 0 here is the half-dismantled one
    if (new.stamina or 0) == 0 and (old.stamina or 0) ~= 0 then
      kept[#kept + 1] = name
      return old
    end
    return new
  end
  if name == "position" then
    if new.x == nil and old.x ~= nil and old.zone == new.zone then
      kept[#kept + 1] = name
      return old
    end
    return new
  end
  for k, v in pairs(old) do
    if holdsNothing(new[k]) and not holdsNothing(v) then
      new[k] = v
      kept[#kept + 1] = name .. "." .. tostring(k)
    end
  end
  return new
end

local function snapshot(reason)
  local rec = charRecord()
  if not rec then return end
  rec.errors = {}
  rec.saved = nowTime()
  rec.reason = reason
  lastSnapshot = rec.saved
  local kept = {}
  local ok, id = pcall(collectIdentity)
  if ok then
    for k, v in pairs(id) do
      if reason == "logout" and LOGOUT_ZERO[k] and v == 0 and type(rec[k]) == "number" and rec[k] ~= 0 then
        kept[#kept + 1] = k
      else
        rec[k] = v
      end
    end
  else
    rec.errors.identity = tostring(id)
  end
  local parts = {
    { "equipped", collectEquipped }, { "stats", collectStats }, { "position", collectPosition },
    { "skills", collectSkills }, { "reputation", collectReputation }, { "quests", collectQuests },
    { "talents", collectTalents }, { "pet", collectPet }, { "bags", collectBags },
  }
  for _, part in ipairs(parts) do
    local good, res = pcall(part[2])
    if good then
      if reason == "logout" then res = keepAtLogout(part[1], rec[part[1]], res, kept) end
      rec[part[1]] = res
    else
      rec.errors[part[1]] = tostring(res)
    end
  end
  rec.kept = (#kept > 0) and kept or nil
  if next(rec.errors) == nil then rec.errors = nil end
end

-- The vendor or trainer whose window is open. The target is used only when it is a creature: a window opened
-- with another player targeted must never store that player's name.
local function npcInfo()
  local unit = "npc"
  local guid = firstOf(UnitGUID, "npc")
  if type(guid) ~= "string" then
    local target = firstOf(UnitGUID, "target")
    if type(target) == "string" and string.match(target, "^Creature%-") then
      unit, guid = "target", target
    else
      return nil, nil
    end
  end
  if not string.match(guid, "^Creature%-") and not string.match(guid, "^Vehicle%-") then return nil, nil end
  local id = tonumber(string.match(guid, "^%a+%-%d+%-%d+%-%d+%-%d+%-(%d+)"))
  return firstOf(UnitName, unit), id
end

-- nil when the window's owner is not a known creature (then nothing is stored)
local function shortRecord(list)
  local name, id = npcInfo()
  if not id then return nil end
  local pos = collectPosition()
  return { name = name, id = id, map = pos.map, x = pos.x, y = pos.y, zone = pos.zone, sub = pos.sub,
    saved = nowTime(), items = list }, tostring(id)
end

local function note(key, t)
  init()
  DB.notes = DB.notes or {}
  t.saved = nowTime()
  DB.notes[key] = t
end

local function countEvent(event)
  init()
  DB.events = DB.events or {}
  local e = DB.events[event]
  if not e then
    e = { n = 0 }
    DB.events[event] = e
  end
  e.n = e.n + 1
  e.last = nowTime()
end

local tradeTries, trainerTries = 0, 0
-- the list of the trainer window that is open has been read: its own refreshes (TRAINER_UPDATE, also sent when the
-- add-on switches a filter on and back) are not read again until the window closes and opens
local trainerRead = false
-- and however each read turns out (an empty list too), one window is read three times at most
local trainerReadsThisWindow, MAX_TRAINER_READS = 0, 3
local later -- defined with the events below

local function saveTradeSkill(event)
  local rec = charRecord()
  if not rec then return end
  local ok, res = pcall(collectTradeSkill)
  local n = { event = event, ok = ok, tries = tradeTries }
  if ok then
    n.name, n.recipes, n.rank, n.sample = res.name, #res.recipes, res.rank, res.sample
  else
    n.err = tostring(res)
  end
  note("tradeskill", n)
  if ok and #res.recipes > 0 then
    res.sample = nil
    res.name = res.name or "profession"
    res.saved = nowTime()
    rec.tradeskills = rec.tradeskills or {}
    rec.tradeskills[res.name] = res
  elseif tradeTries < 3 then
    tradeTries = tradeTries + 1
    later("trade", 2, function() saveTradeSkill("retry") end)
  end
end

local function saveTrainer(event)
  if trainerRead then return end -- a read that was waiting while this window's list was already read
  trainerReadsThisWindow = trainerReadsThisWindow + 1
  if trainerReadsThisWindow >= MAX_TRAINER_READS then trainerRead = true end -- this is the last one
  local ok, list, info = pcall(collectTrainer)
  local n = { event = event, ok = ok, tries = trainerTries }
  if ok then
    n.count, n.listed, n.sample, n.err = info.count, #list, info.sample, info.err
  else
    n.err = tostring(list)
  end
  note("trainer", n)
  if ok and #list > 0 then
    trainerRead = true
    local entry, key = shortRecord(list)
    if entry then
      entry.services, entry.items = list, nil
      DB.trainers[key] = entry
    end
  elseif trainerTries < 3 then
    trainerTries = trainerTries + 1
    later("trainer", 1.5, function() saveTrainer("retry") end)
  end
end

local function saveMerchant()
  local ok, list = pcall(collectMerchant)
  if not ok or #list == 0 then return end
  local entry, key = shortRecord(list)
  if entry then DB.vendors[key] = entry end
end

local function saveBank()
  local rec = charRecord()
  if not rec then return end
  local bags = { -1 }
  local firstBag = (_G.NUM_BAG_SLOTS or 4) + 1
  for bag = firstBag, firstBag + (_G.NUM_BANKBAGSLOTS or 7) - 1 do bags[#bags + 1] = bag end
  local ok, res = pcall(countItems, bags)
  if ok then rec.bank, rec.bankSaved = res, nowTime() end
end

-- what this client has (so that a missing function can be fixed from the data) ------------------

local PROBES = { "GetInventoryItemLink", "GetItemInfo", "UnitStat", "UnitRangedAttackPower", "GetRangedCritChance",
  "GetNumSkillLines", "GetSkillLineInfo", "GetProfessions", "GetProfessionInfo", "GetNumFactions", "GetFactionInfo",
  "GetNumQuestLogEntries", "GetQuestLogTitle", "GetQuestsCompleted", "GetNumTalentTabs", "GetTalentInfo",
  "GetNumTradeSkills", "GetNumTrainerServices", "GetTrainerServiceInfo", "GetMerchantNumItems", "GetMerchantItemInfo",
  "GetContainerNumSlots", "ReloadUI", "C_Timer", "C_Container", "C_Map", "C_QuestLog", "C_Reputation", "C_TradeSkillUI",
  "C_TrainerUI", "C_MerchantFrame", "C_ClassTalents", "C_Traits", "C_SpellBook", "C_Item", "C_Spell", "C_SkillLine",
  "C_Professions" }
local NAMESPACES = { "C_TrainerUI", "C_MerchantFrame", "C_SkillLine", "C_Professions", "C_ClassTalents", "C_TradeSkillUI",
  "C_Reputation" }

-- every C_ namespace and every function with "Trainer" in its name: the trainer API of this client
local function collectGlobals()
  local trainer, namespaces = {}, {}
  for k, v in pairs(_G) do
    if type(k) == "string" then
      if type(v) == "function" and string.find(k, "Trainer") then trainer[#trainer + 1] = k end
      if type(v) == "table" and string.sub(k, 1, 2) == "C_" then namespaces[#namespaces + 1] = k end
    end
  end
  table.sort(trainer)
  table.sort(namespaces)
  return { trainerFunctions = trainer, namespaces = namespaces }
end

local function collectDiag()
  local d = { has = {}, ns = {}, addon = VERSION, project = _G.WOW_PROJECT_ID }
  for _, name in ipairs(PROBES) do d.has[name] = _G[name] ~= nil end
  for _, name in ipairs(NAMESPACES) do
    local t = _G[name]
    if type(t) == "table" then
      local keys = {}
      for k, v in pairs(t) do
        if type(v) == "function" then keys[#keys + 1] = tostring(k) end
      end
      table.sort(keys)
      d.ns[name] = keys
    end
  end
  local version, build, date, toc = safeCall(GetBuildInfo)
  d.game = { version = version, build = build, date = date, toc = toc }
  d.globals = collectGlobals()
  return d
end

-- events -----------------------------------------------------------------------------------------

-- auto-save (opt-in) -------------------------------------------------------------------------------------

-- WoW writes the saved-variables file only on /reload and on logout. With /fbridge auto on the add-on
-- reloads the UI by itself, but only when everything is quiet: resting in a town or inn, not in combat or an
-- instance, no window open, nothing being typed, something changed, and the file is older than 20 minutes.
-- A 5 second notice comes first; /fbridge stop (or any combat) cancels it.
local AUTO_MIN_AGE = 20 * 60
local loginTime = nowTime()
local dirty = false
local autoPending = false

local BUSY_FRAMES = { "MerchantFrame", "AuctionHouseFrame", "AuctionFrame", "MailFrame", "SendMailFrame", "TradeFrame",
  "BankFrame", "ClassTrainerFrame", "ProfessionsFrame", "TradeSkillFrame", "GossipFrame", "QuestFrame", "WorldMapFrame",
  "CharacterFrame", "SpellBookFrame", "PlayerSpellsFrame", "TalentFrame", "FlightMapFrame", "TaxiFrame",
  -- a question on screen, a ready check, a queue that popped, a loot roll: never reload over them
  "StaticPopup1", "StaticPopup2", "StaticPopup3", "StaticPopup4", "LFGDungeonReadyPopup", "LFGDungeonReadyDialog",
  "LFDRoleCheckPopup", "PVPReadyDialog", "ReadyCheckFrame", "GroupLootFrame1", "GroupLootFrame2", "GroupLootFrame3",
  "GroupLootFrame4", "LootFrame" }

local function safeToReload()
  if _G.InCombatLockdown and InCombatLockdown() then return false end
  if firstOf(UnitAffectingCombat, "player") then return false end
  if firstOf(UnitIsDeadOrGhost, "player") then return false end
  if not firstOf(IsResting) then return false end
  if firstOf(IsInInstance) then return false end
  if firstOf(GetCurrentKeyBoardFocus) then return false end
  if firstOf(UnitCastingInfo, "player") or firstOf(UnitChannelInfo, "player") then return false end  -- a cast, a craft
  for _, name in ipairs(BUSY_FRAMES) do
    local frame = _G[name]
    if type(frame) == "table" and frame.IsShown and firstOf(frame.IsShown, frame) then return false end
  end
  return true
end

local function autoTick()
  if not (DB and DB.auto) or autoPending or not dirty then return end
  if nowTime() - loginTime < AUTO_MIN_AGE then return end
  if not safeToReload() then return end
  autoPending = true
  say("saving in 5 s (/fbridge stop cancels)")
  pcall(function() UIErrorsFrame:AddMessage("ForeverBridge: saving in 5 s", 1, 0.8, 0) end)
  local function go()
    local ok = autoPending and safeToReload()
    autoPending = false
    if ok then
      snapshot("auto")
      if type(ReloadUI) == "function" then ReloadUI() end
    end
  end
  if _G.C_Timer and C_Timer.After then C_Timer.After(5, go) else go() end
end

local waiting = {}

-- run `fn` after `delay` seconds, once however many events asked for it meanwhile
later = function(key, delay, fn)
  if waiting[key] then return end
  waiting[key] = true
  local function run()
    waiting[key] = nil
    pcall(fn)
  end
  if _G.C_Timer and C_Timer.After then
    C_Timer.After(delay, run)
  else
    run()
  end
end

local EVENTS = { "ADDON_LOADED", "PLAYER_LOGIN", "PLAYER_ENTERING_WORLD", "PLAYER_LOGOUT", "PLAYER_EQUIPMENT_CHANGED",
  "BAG_UPDATE_DELAYED", "PLAYER_LEVEL_UP", "SKILL_LINES_CHANGED", "UPDATE_FACTION", "QUEST_LOG_UPDATE", "PLAYER_MONEY",
  "CHARACTER_POINTS_CHANGED", "TRAIT_CONFIG_UPDATED", "ZONE_CHANGED_NEW_AREA", "TRADE_SKILL_SHOW",
  "TRADE_SKILL_LIST_UPDATE", "TRADE_SKILL_UPDATE", "TRADE_SKILL_DATA_SOURCE_CHANGED", "TRADE_SKILL_CLOSE",
  "TRAINER_SHOW", "TRAINER_UPDATE", "TRAINER_CLOSED", "MERCHANT_SHOW", "MERCHANT_UPDATE", "BANKFRAME_OPENED",
  "PLAYER_INTERACTION_MANAGER_FRAME_SHOW", "PLAYER_REGEN_DISABLED" }
for _, event in ipairs(EVENTS) do pcall(frame.RegisterEvent, frame, event) end

local TRAINER_TYPE = (_G.Enum and Enum.PlayerInteractionType and Enum.PlayerInteractionType.Trainer) or 7

local NOT_A_CHANGE = { PLAYER_LOGIN = true, PLAYER_ENTERING_WORLD = true, PLAYER_INTERACTION_MANAGER_FRAME_SHOW = true,
  TRAINER_CLOSED = true, TRADE_SKILL_CLOSE = true }

local function onEvent(_, event, ...)
  local detail = ...
  if event == "ADDON_LOADED" then
    -- every add-on's loading sends this; only our own matters
    if detail == ADDON_NAME then init() end
    return
  end
  init()
  countEvent(event)
  if event == "PLAYER_REGEN_DISABLED" then
    autoPending = false
    return
  end
  if not NOT_A_CHANGE[event] then dirty = true end
  local trainerOpens = event == "TRAINER_SHOW"
    or (event == "PLAYER_INTERACTION_MANAGER_FRAME_SHOW" and detail == TRAINER_TYPE)
  if event == "PLAYER_LOGIN" then
    local good, d = pcall(collectDiag)
    if good then DB.diag = d end
    if _G.C_Timer and C_Timer.NewTicker then pcall(C_Timer.NewTicker, 30, autoTick) end
    later("snapshot", 4, function() snapshot("login") end)
    say("ready: /fbridge save refreshes the file the Forever Guide reads")
  elseif event == "PLAYER_LOGOUT" then
    snapshot("logout")
  elseif event == "TRADE_SKILL_SHOW" then
    tradeTries = 0
    later("trade", 1.5, function() saveTradeSkill(event) end)
  elseif event == "TRADE_SKILL_LIST_UPDATE" or event == "TRADE_SKILL_UPDATE" or event == "TRADE_SKILL_DATA_SOURCE_CHANGED" then
    later("trade", 1.5, function() saveTradeSkill(event) end)
  elseif trainerOpens then
    trainerTries, trainerRead, trainerReadsThisWindow = 0, false, 0
    later("trainer", 1, function() saveTrainer(event) end)
  elseif event == "TRAINER_UPDATE" then
    if not trainerRead then later("trainer", 1, function() saveTrainer(event) end) end
  elseif event == "TRAINER_CLOSED" then
    trainerRead, trainerReadsThisWindow = false, 0
  elseif event == "TRADE_SKILL_CLOSE" or event == "PLAYER_INTERACTION_MANAGER_FRAME_SHOW" then
    -- counted above, nothing to read
  elseif event == "MERCHANT_SHOW" or event == "MERCHANT_UPDATE" then
    later("merchant", 0.7, saveMerchant)
  elseif event == "BANKFRAME_OPENED" then
    later("bank", 0.7, saveBank)
  else
    later("snapshot", 3, function() snapshot(event) end)
  end
end

frame:SetScript("OnEvent", onEvent)

SLASH_FOREVERBRIDGE1 = "/fbridge"
SlashCmdList["FOREVERBRIDGE"] = function(msg)
  msg = string.lower(msg or "")
  if msg == "save" then
    snapshot("save")
    if _G.InCombatLockdown and InCombatLockdown() then
      say("saved in memory; you are in combat, type /reload when it is over")
    elseif type(ReloadUI) == "function" then
      say("saved, reloading the UI so that the file is written")
      ReloadUI()
    end
  elseif msg == "diag" then
    init()
    local d = DB.diag or collectDiag()
    local missing = {}
    for name, has in pairs(d.has or {}) do
      if not has then missing[#missing + 1] = name end
    end
    table.sort(missing)
    say("client " .. tostring(d.game and d.game.version) .. " build " .. tostring(d.game and d.game.build) ..
      "; missing: " .. (next(missing) and table.concat(missing, ", ") or "nothing"))
  elseif msg == "auto on" or msg == "auto off" then
    init()
    DB.auto = (msg == "auto on")
    say(DB.auto and "auto-save is ON: the UI reloads by itself while you rest in a town, nothing open, not in combat, at most every 20 minutes (/fbridge stop cancels one, /fbridge auto off turns it off)"
      or "auto-save is OFF")
  elseif msg == "stop" then
    autoPending = false
    say("cancelled")
  else
    init()
    local age = lastSnapshot > 0 and (nowTime() - lastSnapshot) or nil
    say((age and ("snapshot taken " .. age .. " s ago; the file is written on /reload and on logout (/fbridge save does both)")
      or "no snapshot yet in this session") .. "; auto-save is " .. (DB.auto and "on" or "off") .. " (/fbridge auto on|off)")
  end
end
