'use strict';
const crypto = require('node:crypto');

const SAVE_KEYS = {
  UserAbilityOrbMaterial: ['userId','materialId'], UserAbilityOrbSlotBase: ['userId','slotNumber'],
  UserAchievement: ['userId','achievementId'], UserAdventureStage: ['userId','adventureStageId'],
  UserAlchemicItem: ['userId','alchemicItemId'], UserArea: ['userId','areaId'],
  UserAreaEnemy: ['userId','areaObjectId'], UserAreaFlag: ['userId','areaFlagId'],
  UserAuctionBroker: ['userId','brokerId'], UserAuctionBuyItem: ['userId','auctionBuyItemId'],
  UserAuctionNamedBroker: ['userId','brokerId'], UserAuctionSkill: ['userId','skillID'],
  UserAuctionTreasure: ['userId','auctionTreasureId'], UserAutoEffectItem: ['userId','autoEffectItemId'],
  UserAutoEffectItemGroup: ['userId','contentType'], UserBattleDifficultyGroup: ['userId','contentId'],
  UserBattleReturnMatch: ['userId','battleReturnMatchId'], UserBattleRushCourse: ['userId','battleRushCourseId'],
  UserBattleRushStage: ['userId','battleRushStageId'], UserBattleRushWave: ['userId','battleRushWaveId'],
  UserBikeGameResult: ['userId','courseId'], UserBuddy: ['userId','buddyId'],
  UserBuddyChangeType: ['userId','buddyChangeTypeId'], UserBuddyEquipmentSpecie: ['userId','equipmentId'],
  UserBuddyEquipmentStock: ['userId','id'], UserBuddyItem: ['userId','buddyItemId'],
  UserBuddyStyle: ['userId','buddyStyleId'], UserCatDiaryChain: ['userId','id'],
  UserCatDiaryChainLocation: ['userId','id'], UserCipherText: ['userId','cipherTextId'],
  UserCoalmineFacility: ['userId','id'], UserCoalmineItem: ['userId','id'],
  UserCollabo: ['userId','collaboId'], UserCollabo08CollectItem: ['userId','itemId'],
  UserCollabo08CoreItem: ['userId','pcStyleId'], UserCollabo08CreateItem: ['userId','itemId'],
  UserCollabo08EquipmentStockOfCoreItem: ['userId','id'], UserCollabo08Recipe: ['userId','recipeId'],
  UserCollabo09AbilitySet: ['userId','pcStyleId'], UserCollabo09EquipmentSet: ['userId','pcStyleId'],
  UserCollabo09EquipmentStock: ['userId','equipmentStockId'], UserCollabo09GraphItem: ['userId','collabo09GraphItemId'],
  UserCollabo09Proficiency: ['userId','pcStyleId'], UserColosseumPassiveEffect: ['userId','passiveEffectId'],
  UserConsumableItem: ['userId','consumableItemId'], UserContentCorrectionInfo: ['userId','type'],
  UserCookingMaterial: ['userId','cookingMaterialId'], UserCookingMenu: ['userId','menuId'],
  UserCounter: ['userId','counterId'], UserCurrency: ['userId','currencyId'],
  UserDailyBonus: ['userId','dailyBonusId'], UserDanshou: ['userId','danshouId'],
  UserDestinyItem: ['userId','destinyItemId'], UserDungeon: ['userId','dungeonId'],
  UserDungeonFlag: ['userId','dungeonFlagId'], UserDungeonTicket: ['userId','dungeonTicketId'],
  UserEnchantWeapon: ['userId','enchantWeaponId'], UserEnchantWeaponBoss: ['userId','enchantWeaponBossId'],
  UserEnchantWeaponBossResultList: ['userId','enchantWeaponBossId'],
  UserEnchantWeaponShopItem: ['userId','enchantWeaponShopItemId'],
  UserEnchantWeaponSlotItem: ['userId','enchantWeaponSlotItemId'], UserEnemyParty: ['userId','enemyPartyId'],
  UserEnemySpecie: ['userId','enemySpecieId'], UserEnvironmentChangeGroup: ['userId','groupId'],
  UserEquipmentSpecie: ['userId','equipmentId'], UserEquipmentStock: ['userId','id'],
  UserEquipmentStockOfAbilityOrb: ['userId','id'], UserEquipmentStockOfElementBadge: ['userId','id'],
  UserEquipmentStockOfRune: ['userId','id'], UserExpItem: ['userId','expItemId'],
  UserFestival: ['userId','festivalId'], UserFish: ['userId','fishId'],
  UserFishCollectingFeed: ['userId','fishCollectingFeedId'],
  UserFishCollectingFishSpecie: ['userId','fishCollectingFishSpecieId'],
  UserFishCollectingFishStock: ['userId','id'], UserFishCollectingItem: ['userId','id'],
  UserFishCollectingPlace: ['userId','areaObjectId'], UserFishFood: ['userId','id'],
  UserFishingPlace: ['userId','areaObjectId'], UserFishItem: ['userId','id'],
  UserFishSpecie: ['userId','fishId'], UserFishStock: ['userId','id'],
  UserFortuneAreaRoute: ['userId','fortuneAreaRouteId'], UserFreeze: ['userId','freezeId'],
  UserFriendsInvitationGuest: ['userId','invitationId'], UserFriendsInvitationHost: ['userId','invitationId'],
  UserGaiden: ['userId','gaidenId'], UserGaishi: ['userId','gaishiId'],
  UserGameManual: ['userId','gameManualId'], UserGenericItem: ['userId','genericItemId'],
  UserGift: ['userId','id'], UserGimmickItem: ['userId','gimmickItemId'],
  UserGlobalFlag: ['userId','globalFlagId'], UserHelixCollectItem: ['userId','collectItemId'],
  UserHelixCraftItem: ['userId','craftItemId'], UserHelixCraftRecipe: ['userId','craftRecipeId'],
  UserHelixRecordItem: ['userId','recordItemId'], UserHelixStarItem: ['userId','starItemId'],
  UserIGRPGFriend: ['userId','igrpgFriendId'], UserItemToken: ['userId','signature'],
  UserJobRankItem: ['userId','jobRankItemId'], UserJobRankItemTicket: ['userId','jobRankItemTicketId'],
  UserKaikouCondition: ['userId','conditionId'], UserKaikouFlag: ['userId','kaikouFlagId'],
  UserKeyConfig: ['userId','id'], UserKeyItem: ['userId','keyItemId'],
  UserLimitedLotteryTicket: ['userId','lotteryTicketId'], UserLocation: ['userId','locationId'],
  UserLocationFlag: ['userId','locationFlagId'], UserLottery: ['userId','lotteryExId'],
  UserLotteryTicket: ['userId','lotteryTicketId'], UserMaterial: ['userId','materialId'],
  UserMigratoryEnemy: ['userId','migratoryEnemyId'], UserMysteryEventInfo: ['userId','mysteryEventInfoId'],
  UserMysteryFlag: ['userId','mysteryFlagId'], UserMysteryItem: ['userId','mysteryItemId'],
  UserNotice: ['userId','id'], UserOperaBook: ['userId','operaBookId'],
  UserOperaFlag: ['userId','operaFlagId'], UserOperaPCRanking: ['userId','operaPCRankingId'],
  UserOperaRole: ['userId','operaRoleId'], UserOrdealAchievementStock: ['userId','id'],
  UserPackProduct: ['userId','packProductId'], UserPackProductViewedState: ['userId','packProductId'],
  UserParty: ['userId','id'], UserPartyPosition: ['userId','partyId'], UserPartySquad: ['userId','partyId'],
  UserPaymentPointCard: ['userId','paymentPointCardId'], UserPC: ['userId','pcId'],
  UserPCCostume: ['userId','costumeId'], UserPCCostumeProduct: ['userId','costumeProductId'],
  UserPCCostumeProductViewedState: ['userId','costumeProductId'], UserPCCostumeWearState: ['userId','costumeId'],
  UserPCElementBadge: ['userId','pcStyleId'], UserPCFavoriteEquipment: ['userId','pcFavoriteEquipmentId'],
  UserPCJobSet: ['userId','pcId'], UserPCPartyJoin: ['userId','pcId'], UserPCStyle: ['userId','pcStyleId'],
  UserPCStyleZodiac: ['userId','pcStyleZodiacId'], UserPCTag: ['userId','pcTagId'], UserPet: ['userId','petId'],
  UserPetEnemyParty: ['userId','enemyPartyId'], UserPetEquipmentSpecie: ['userId','petEquipmentId'],
  UserPetEquipmentStock: ['userId','id'], UserPetFood: ['userId','petFoodId'],
  UserPetFoodBox: ['userId','petFoodBoxId'], UserPetFurniture: ['userId','petFurnitureId'],
  UserPetHouse: ['userId','petHouseId'], UserPetHouseArrangement: ['userId','petHouseArrangementId'],
  UserPetMaterial: ['userId','petMaterialId'], UserPetParty: ['userId','partyId'],
  UserPetRoomExpansion: ['userId','petRoomExpansionId'], UserPetRoomReform: ['userId','petRoomReformId'],
  UserPetSkillDeck: ['userId','petSkillDeckId'], UserPetToy: ['userId','petToyId'],
  UserPresetEquipment: ['userId','presetEquipmentId'], UserQuest: ['userId','questId'],
  UserQuestFlag: ['userId','questFlagId'], UserRaidBattleEnemyParty: ['userId','enemyObjectId'],
  UserRaidBattleParty: ['userId','partyId'], UserRandomSeed: ['userId','signature'],
  UserRepeatableQuestStep: ['userId','questStepId'], UserRetsuden: ['userId','retsudenId'],
  UserRoguelikeDungeon: ['userId','dungeonId'], UserSerialStory: ['userId','serialStoryId'],
  UserSkitEvent: ['userId','skitEventId'], UserSkyTownEvent: ['userId','eventId'],
  UserSkyTownStatus: ['userId','skyTownId'], UserSkyTownWorker: ['userId','workerId'],
  UserStarLibraryBookStatus: ['userId','bookId'], UserStarLibraryLevel: ['userId','starLibraryLevelId'],
  UserStarLibraryMissionStatus: ['userId','missionId'],
  UserStarLibraryScoreAttackInfo: ['userId','starLibraryScoreAttackInfoId'],
  UserStarLibraryScoreAttackReward: ['userId','starLibraryScoreAttackRewardId'],
  UserStoryEpisodeFlag: ['userId','storyEpisodeFlagId'], UserStoryPart: ['userId','storyPartId'],
  UserStoryStep: ['userId','storyStepId'], UserSystemFlag: ['userId','systemFlagId'],
  UserTokenShopCommodity: ['userId','id'], UserTreasure: ['userId','treasureId'],
  UserUnitFriendship: ['userId','targetId'], UserUnknownEquipment: ['userId','unknownEquipmentId'],
  UserUnknownEquipmentStock: ['userId','id'], UserVessel: ['userId','vesselId'],
};
const md5 = value => crypto.createHash('md5').update(value).digest('hex');
function invalid(message) { throw Object.assign(new Error(message), { status: 400 }); }
function requireValue(value, message) { if (!value) invalid(message); }
const sameKeys = (value, keys) => value && !Array.isArray(value) && Object.keys(value).sort().join(',') === [...keys].sort().join(',');
function identityMatches(value, userId) {
  if (Array.isArray(value)) return value.every(item => identityMatches(item, userId));
  if (!value || typeof value !== 'object') return true;
  return (!Object.hasOwn(value, 'userId') || value.userId === userId) && Object.values(value).every(item => identityMatches(item, userId));
}
function mutationKeys(name, current, rows) {
  if (!Array.isArray(current)) { requireValue(rows.length === 1, `Unsupported singleton table ${name}`); return []; }
  const keys = SAVE_KEYS[name];
  requireValue(keys && rows.every(row => keys.every(key => Object.hasOwn(row, key))) &&
    new Set(rows.map(row => JSON.stringify(keys.map(key => row[key])))).size === rows.length,
  `Unsupported table identity ${name} fields=${Object.keys(rows[0] ?? {}).sort().join(',')}`);
  return keys;
}
function upsert(table, rows, keys) {
  if (!Array.isArray(table)) return { ...table, ...rows[0] };
  const result = table.map(row => ({ ...row }));
  for (const row of rows) {
    const index = result.findIndex(old => keys.every(key => old[key] === row[key]));
    if (index < 0) result.push({ ...row }); else result[index] = { ...result[index], ...row };
  }
  return result;
}
function remove(table, rows, keys) {
  if (!Array.isArray(table)) return null;
  return table.filter(old => !rows.some(row => keys.every(key => old[key] === row[key])));
}
function preserveEquipmentStockCounter(tables) {
  const info = tables.UserInfo;
  if (!info) return false;
  requireValue(Number.isSafeInteger(info.lastEquipmentStockId) && info.lastEquipmentStockId >= 0,
    'Invalid equipment stock counter');
  let highWater = 0;
  for (const name of ['UserEquipmentStock','UserEquipmentStockOfAbilityOrb','UserEquipmentStockOfElementBadge']) {
    for (const row of tables[name] ?? []) {
      requireValue(Number.isSafeInteger(row.id) && row.id > 0, `Invalid equipment stock id ${name}`);
      highWater = Math.max(highWater, row.id);
    }
  }
  if (info.lastEquipmentStockId >= highWater) return false;
  tables.UserInfo = { ...info, lastEquipmentStockId: highWater };
  return true;
}

function applySave(value, { userId, tables, tokenAliases = {} }) {
  const table = name => tables[name];
  const currentTokens = Object.fromEntries(Object.entries(tables).map(([name, rows]) => [name, md5(JSON.stringify(rows))]));
  for (const [alias, name] of Object.entries(tokenAliases)) currentTokens[alias] = currentTokens[name];
  requireValue(sameKeys(value, ['badges','checksums','dataTokens','deltas','giftIds','operations','scripts','surplus']) &&
    Array.isArray(value.deltas) && value.deltas.length >= 1 && value.deltas.length <= 32 && Array.isArray(value.giftIds) && value.giftIds.length === 0 &&
    Array.isArray(value.operations) && value.operations.length === 0 && Array.isArray(value.surplus) && value.surplus.length === 0,
  'Unsupported save envelope');
  const mutations = value.deltas.map(delta => {
    requireValue(sameKeys(delta, ['deleteItems','putItems','signature','trigger']) && delta.signature === 0 &&
      typeof delta.trigger === 'string' && /^[A-Za-z][A-Za-z0-9_]{0,63}$/.test(delta.trigger) &&
      delta.putItems && typeof delta.putItems === 'object' && !Array.isArray(delta.putItems) &&
      delta.deleteItems && typeof delta.deleteItems === 'object' && !Array.isArray(delta.deleteItems), 'Unsupported save transaction');
    const puts = Object.keys(delta.putItems).sort(), deletes = Object.keys(delta.deleteItems).sort();
    requireValue(puts.length + deletes.length >= 1, 'Empty save transaction');
    return { delta, puts, deletes };
  });
  const mutationNames = [...new Set(mutations.flatMap(item => [...item.puts, ...item.deletes]))].sort();
  requireValue(mutationNames.every(name => Object.hasOwn(tables, name)) && sameKeys(value.dataTokens, mutationNames) &&
    sameKeys(value.checksums, ['after','before']) && sameKeys(value.checksums.before, mutationNames) &&
    sameKeys(value.checksums.after, mutationNames), 'Unsupported save transaction');
  for (const name of mutationNames) requireValue(/^[0-9a-f]{32}$/.test(value.dataTokens[name]) &&
    value.dataTokens[name] === currentTokens[name] && /^[0-9a-f]{32}$/.test(value.checksums.before[name]) &&
    /^[0-9a-f]{32}$/.test(value.checksums.after[name]), 'Invalid save table');
  // ponytail: local single-player compatibility trusts authenticated client deltas; add domain rules before multiplayer.
  const nextTables = { ...tables }, putCounts = {}, deleteCounts = {}, data = {};
  for (const { delta, puts, deletes } of mutations) {
    for (const name of [...puts, ...deletes]) {
      const rows = delta.putItems[name] ?? delta.deleteItems[name], current = nextTables[name];
      requireValue(Array.isArray(rows) && rows.length >= 1 && rows.length <= Math.max(Array.isArray(current) ? current.length : 1, 4096) &&
        identityMatches(rows, userId), 'Invalid save table');
      mutationKeys(name, current, rows);
    }
    for (const name of puts) {
      const rows = delta.putItems[name], current = nextTables[name];
      nextTables[name] = upsert(current, rows, mutationKeys(name, current, rows));
      putCounts[name] = (putCounts[name] ?? 0) + rows.length;
    }
    for (const name of deletes) {
      const rows = delta.deleteItems[name], current = nextTables[name];
      nextTables[name] = remove(current, rows, mutationKeys(name, current, rows));
      deleteCounts[name] = (deleteCounts[name] ?? 0) + rows.length;
    }
  }
  if (mutationNames.includes('UserInfo')) preserveEquipmentStockCounter(nextTables);
  const itemTokenCount = deleteCounts.UserItemToken ?? 0;
  if (itemTokenCount) {
    data.UserItemToken = Array.from({ length: itemTokenCount }, () =>
      ({ userId, signature: crypto.randomInt(1, 0x80000000) }));
    nextTables.UserItemToken.push(...data.UserItemToken.map(row =>
      ({ consumer: 0, context: '', signature: row.signature, userId: row.userId, value: 0, verifier: '' })));
  }
  const randomSeedCount = deleteCounts.UserRandomSeed ?? 0;
  if (randomSeedCount) {
    data.UserRandomSeed = Array.from({ length: randomSeedCount }, () => ({ userId,
      dynamoDbExpiredAt: Math.floor(Date.now() / 1000) + 86400, seed: crypto.randomInt(1, 0x80000000),
      signature: crypto.randomInt(1, 0x80000000) }));
    nextTables.UserRandomSeed.push(...data.UserRandomSeed.map(row => ({ consumer: 0,
      dynamoDbExpiredAt: row.dynamoDbExpiredAt, result: [], seed: row.seed, signature: row.signature,
      userId: row.userId, verifier: '' })));
  }
  const nextTokens = Object.fromEntries(Object.entries(nextTables).map(([name, rows]) => [name, md5(JSON.stringify(rows))]));
  for (const [alias, name] of Object.entries(tokenAliases)) nextTokens[alias] = nextTokens[name];
  const responseTokenNames = [...mutationNames];
  if (mutationNames.includes('UserItemToken')) responseTokenNames.push('ItemTokens');
  if (mutationNames.includes('UserRandomSeed')) responseTokenNames.push('RandomSeeds');
  return { mutationNames, nextTables, response: { code: 0, triggers: mutations.map(item => item.delta.trigger), putItems: putCounts,
    deleteItems: Object.keys(deleteCounts).length ? deleteCounts : [], data, operations: [], dones: [],
    dataTokens: Object.fromEntries(responseTokenNames.map(name => [name, nextTokens[name]])) } };
}

module.exports = { SAVE_KEYS, applySave, mutationKeys, preserveEquipmentStockCounter };
