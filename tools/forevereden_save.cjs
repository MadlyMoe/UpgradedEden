'use strict';
const crypto = require('node:crypto');

const SAVE_KEYS = {
  UserAreaEnemy: ['userId','areaObjectId'], UserCatDiary: ['userId','termId'], UserGameManual: ['userId','gameManualId'],
  UserDungeonTicket: ['userId','dungeonTicketId'], UserEnvironmentChangeGroup: ['userId','groupId','tableId','tableIndex'],
  UserEquipmentSpecie: ['userId','equipmentId'], UserFreeze: ['userId'], UserGlobalFlag: ['userId','globalFlagId'],
  UserInfo: ['userId'], UserKeyItem: ['userId','keyItemId'], UserMigratoryEnemy: ['userId','migratoryEnemyId'],
  UserOrdealAchievementStock: ['userId','id'], UserPC: ['userId','pcId'], UserPCJobSet: ['userId','pcId'],
  UserPCStyle: ['userId','pcStyleId'], UserParty: ['userId','id'], UserStoryStep: ['userId','storyStepId'],
  UserSystemFlag: ['userId','systemFlagId'],
  UserItemToken: ['userId','consumer','value'], UserMaterial: ['userId','materialId'], UserRandomSeed: ['userId','consumer'],
  UserTreasure: ['userId','treasureId'],
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
  if (!Array.isArray(current)) return [];
  let keys = SAVE_KEYS[name] ?? (rows.every(row => row && typeof row === 'object' && Object.hasOwn(row, '_id')) ? ['_id'] : null);
  if (!keys) {
    const conventional = `${name.replace(/^User/, '')}Id`.toLowerCase();
    const candidates = Object.keys(rows[0] ?? {}).filter(key => key !== 'userId' && key.toLowerCase() === conventional);
    if (candidates.length === 1 && rows.every(row => Object.hasOwn(row, candidates[0]))) keys = ['userId', candidates[0]];
  }
  requireValue(keys && rows.every(row => keys.every(key => Object.hasOwn(row, key))) &&
    new Set(rows.map(row => JSON.stringify(keys.map(key => row[key])))).size === rows.length, `Unsupported table identity ${name}`);
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
  const itemTokenCount = (putCounts.UserItemToken ?? 0) + (deleteCounts.UserItemToken ?? 0);
  if (itemTokenCount) data.UserItemToken = Array.from({ length: itemTokenCount }, () =>
    ({ userId, signature: crypto.randomInt(1, 0x80000000) }));
  const randomSeedCount = (putCounts.UserRandomSeed ?? 0) + (deleteCounts.UserRandomSeed ?? 0);
  if (randomSeedCount) data.UserRandomSeed = Array.from({ length: randomSeedCount }, () => ({ userId,
    dynamoDbExpiredAt: Math.floor(Date.now() / 1000) + 86400, seed: crypto.randomInt(1, 0x80000000),
    signature: crypto.randomInt(1, 0x80000000) }));
  const nextTokens = Object.fromEntries(Object.entries(nextTables).map(([name, rows]) => [name, md5(JSON.stringify(rows))]));
  for (const [alias, name] of Object.entries(tokenAliases)) nextTokens[alias] = nextTokens[name];
  const responseTokenNames = [...mutationNames];
  if (mutationNames.includes('UserItemToken')) responseTokenNames.push('ItemTokens');
  if (mutationNames.includes('UserRandomSeed')) responseTokenNames.push('RandomSeeds');
  return { mutationNames, nextTables, response: { code: 0, triggers: mutations.map(item => item.delta.trigger), putItems: putCounts,
    deleteItems: Object.keys(deleteCounts).length ? deleteCounts : [], data, operations: [], dones: [],
    dataTokens: Object.fromEntries(responseTokenNames.map(name => [name, nextTokens[name]])) } };
}

module.exports = { applySave };
