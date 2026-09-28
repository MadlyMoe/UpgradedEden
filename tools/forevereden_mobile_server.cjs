'use strict';
// Dependency-free startup server for the Android launcher.
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');
const zlib = require('node:zlib');
const { encryptBody, decryptBody, encodeMsgpack } = require('./forevereden_transport.cjs');
const { SAVE_KEYS, mutationKeys } = require('./forevereden_save.cjs');

const PREFIX = /^\/(?:us|ap|eu)\/private\/(game_client|asset)\//;
const ACTIONS = new Set([
  'battle/continue','battle/subscription/continue','battle_rush/reward','cat_diary/reward','dungeon/complete',
  'dungeon/ticket/issue','friends_invitation/common/confirm','friends_invitation/common/initialize',
  'friends_invitation/guest/initialize','gift/receive','incentive/adcolony/issue','incentive/battlecontinue/issue',
  'incentive/dailybonus/issue','incentive/rewardtap/issue','incentive/treasurebox/issue','lottery/draw',
  'matching_user/game_user_id','pack_product/acquire','payment_point/history','pc_costume/acquire','quest/close',
  'serial_code/consume','serial_code/user_data/import','star_library/level_reward','star_library/mission_reward',
  'star_library/score_attack_reward','subscription_ticket/detail','user/game_user_id_for_eu','user/login',
  'user/migration/confirm','user/migration/reserve','user/migration/status','user/migration/status_reset','user/update_meta',
  'user_data/confirm','user_data/delete','user_data/pull','user_data/push',
]);
const SEMANTIC_ROUTES = new Set([
  'battle/continue','battle_rush/reward','dungeon/ticket/issue','gift/receive','lottery/draw','matching_user/game_user_id','quest/close',
  'star_library/level_reward','star_library/mission_reward','star_library/score_attack_reward',
  'user/game_user_id_for_eu','user/login','user/migration/status','user/migration/status_reset','user/update_meta',
  'user_data/confirm','user_data/pull','user_data/push',
]);
const BOOTSTRAP = new Set(['matching_user/game_user_id','user/game_user_id_for_eu','user/login','user/update_meta']);
const CLIENT_SAVE_ACTIONS = {
  'battle_rush/reward': ['stageId','courseId','missionIds'], 'cat_diary/reward': ['lotteryDt','slotNo','step'],
  'dungeon/complete': ['dungeonId'], 'dungeon/ticket/issue': ['id','num'], 'gift/receive': ['userId','giftIds'],
  'pack_product/acquire': ['packProductId'], 'pc_costume/acquire': ['pcCostumeProductId'], 'quest/close': ['id'],
  'star_library/level_reward': ['levelIds'], 'star_library/mission_reward': ['missionIds','bookId'],
  'star_library/score_attack_reward': ['scoreAttackRewardIds'],
};
const LIMITS = { plaintext: 16 * 1024 * 1024, ciphertext: 4 * 1024 * 1024 };
const stone = (id, amount, bonus, priority) => ({
  product_id: `games.wfs.anothereden.gem.${id}`, name: `${amount + bonus} Chronos Stones`, price: '0.01',
  formatted_price: '$0.01', description: 'ForeverEden local Chronos Stones', thumbnail_url: '',
  country_code: 'US', currency_code: 'USD', charge_gem: amount, free_gem: bonus, bonus_gem: 0,
  total_gem: amount + bonus, product_type: 0, priority,
});
const BILLING_PRODUCTS = [
  stone('0011', 25, 5, 1), stone('0012', 135, 20, 2), stone('0013', 280, 35, 3),
  stone('0014', 500, 60, 4), stone('0015', 1040, 120, 5), stone('0017', 3150, 350, 6),
];
const BILLING_BY_ID = new Map(BILLING_PRODUCTS.map(product => [product.product_id, product]));
const LOTTERY_CATALOG = JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(__dirname, 'forevereden_lottery_3_17_0.bin'))));
if (LOTTERY_CATALOG.version !== '3.17.0' || Object.keys(LOTTERY_CATALOG.banners).length !== 3352 ||
    Object.keys(LOTTERY_CATALOG.pools).length !== 1334) throw new Error('Invalid 3.17.0 lottery catalog');
const REWARD_CATALOG = JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(__dirname, 'forevereden_rewards_3_17_0.bin'))));
if (REWARD_CATALOG.version !== '3.17.0' || REWARD_CATALOG.content_generation !== 'ec741d3cc2f29b867892b1ed16a7a59b40e3968d' ||
    REWARD_CATALOG.source_sha256 !== '18c811dabc2a3184c81155a54a234dce64ab23e2eebac4ae1cdfde2ee76386eb' ||
    REWARD_CATALOG.dungeons.length !== 369 || Object.keys(REWARD_CATALOG.quests).length !== 1151 ||
    REWARD_CATALOG.consume?.battle_continue !== 50 || Object.keys(REWARD_CATALOG.consume.dungeon_tickets).length !== 10)
  throw new Error('Invalid 3.17.0 reward catalog');
function weightedStock(pool) {
  const rarityRates = new Map();
  for (const stock of pool) rarityRates.set(stock[2], (rarityRates.get(stock[2]) ?? 0) + stock[3]);
  const total = [...rarityRates.values()].reduce((sum, rate) => sum + rate, 0);
  requireValue(Number.isSafeInteger(total) && total > 0, 'Banner requires an explicit encounter');
  let roll = crypto.randomInt(total);
  let rarity;
  for (const entry of rarityRates) if ((roll -= entry[1]) < 0) { rarity = entry[0]; break; }
  const candidates = pool.filter(stock => stock[2] === rarity);
  const candidateTotal = candidates.reduce((sum, stock) => sum + stock[3], 0);
  requireValue(candidateTotal > 0, 'Profile has no renderable character for lottery rarity');
  roll = crypto.randomInt(candidateTotal);
  for (const stock of candidates) if ((roll -= stock[3]) < 0) return stock;
  throw new Error('Lottery weight selection failed');
}
const hash = (value, algorithm = 'sha256') => crypto.createHash(algorithm).update(value).digest('hex');
function fail(status, message) { throw Object.assign(new Error(message), { status }); }
function requireValue(value, message) { if (!value) fail(400, message); }
const sameKeys = (value, keys) => value && !Array.isArray(value) && Object.keys(value).sort().join(',') === [...keys].sort().join(',');
function localRows(rows, userId) {
  requireValue(rows.every(row => row && typeof row === 'object' && !Array.isArray(row) &&
    (!Object.hasOwn(row, 'userId') || Number.isSafeInteger(row.userId) && row.userId > 0)), 'Invalid local profile row');
  return rows.map(row => Object.hasOwn(row, 'userId') ? { ...row, userId } : row);
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
function atomicJson(file, value) {
  const body = `${JSON.stringify(value)}\n`, temporary = `${file}.tmp-${process.pid}`;
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(temporary, body, { mode: 0o600, flag: 'wx' });
  if (fs.existsSync(file)) fs.copyFileSync(file, `${file}.bak`);
  fs.renameSync(temporary, file);
}

function createMobileServer({ seed, codec, statePath, database, initialState, resources = new Map(), log = console.log }) {
  const key = Buffer.from(codec.key_hex, 'hex'), fallbackIV = Buffer.from(codec.fallback_iv_hex, 'hex');
  if (key.length !== 32 || fallbackIV.length !== 16 || !Number.isSafeInteger(seed.user_id) || Object.keys(seed.tables ?? {}).length !== 207)
    throw new Error('Invalid mobile runtime inputs');
  const collectionTables = Object.entries(seed.tables).filter(([, value]) => Array.isArray(value)).map(([name]) => name).sort();
  if (JSON.stringify(collectionTables) !== JSON.stringify(Object.keys(SAVE_KEYS).sort()))
    throw new Error('Save identity catalog does not cover the local profile');
  if (Boolean(statePath) === Boolean(database)) throw new Error('Choose one profile store');
  const freshState = () => ({ version: 1, user_id: seed.user_id, capability: crypto.randomBytes(16).toString('hex'),
    aes_iv: crypto.randomBytes(8).toString('hex'), device_hash: null, last_sequence: '-1', meta: {}, tables: {}, replies: {},
    next_operation_id: 1, pending_operations: {}, claims: {} });
  const validState = state => state.version === 1 && state.user_id === seed.user_id &&
    typeof state.capability === 'string' && state.capability.length === 32 &&
    typeof state.aes_iv === 'string' && Buffer.byteLength(state.aes_iv) === 16 &&
    state.replies && typeof state.replies === 'object' && !Array.isArray(state.replies) &&
    (state.tables === undefined || state.tables && typeof state.tables === 'object' && !Array.isArray(state.tables) &&
      Object.keys(state.tables).every(name => Object.hasOwn(seed.tables, name)));
  let state, db = null, newStore = false;
  if (database) {
    const { DatabaseSync } = require('node:sqlite');
    fs.mkdirSync(path.dirname(database), { recursive: true });
    db = new DatabaseSync(database);
    try {
      if (db.prepare('PRAGMA quick_check').get().quick_check !== 'ok') throw new Error('quick_check failed');
    } catch (error) {
      db.close();
      throw new Error('Corrupt SQLite profile', { cause: error });
    }
    db.exec('PRAGMA busy_timeout=3000; PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;');
    const version = db.prepare('PRAGMA user_version').get().user_version;
    if (version !== 0 && version !== 1) throw new Error('Unsupported mobile profile schema');
    if (version === 0) {
      db.exec(`CREATE TABLE runtime (id INTEGER PRIMARY KEY CHECK(id=1), user_id INTEGER NOT NULL, seed_hash TEXT NOT NULL);
        CREATE TABLE server_state (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL);
        CREATE TABLE profile (name TEXT PRIMARY KEY, data TEXT NOT NULL, token TEXT NOT NULL);`);
      state = structuredClone(initialState ?? freshState()); state.tables ??= {};
      if (!validState(state)) throw new Error('Invalid mobile server state');
      const overrides = state.tables, seedHash = hash(JSON.stringify(seed));
      db.exec('BEGIN IMMEDIATE');
      try {
        db.prepare('INSERT INTO runtime VALUES(1,?,?)').run(seed.user_id, seedHash);
        const insert = db.prepare('INSERT INTO profile VALUES(?,?,?)');
        for (const [name, original] of Object.entries(seed.tables)) {
          const data = JSON.stringify(Object.hasOwn(overrides, name) ? overrides[name] : original);
          insert.run(name, data, hash(data, 'md5'));
        }
        const saved = { ...state }; delete saved.tables;
        db.prepare('INSERT INTO server_state VALUES(1,?)').run(JSON.stringify(saved));
        db.exec('PRAGMA user_version=1; COMMIT;'); newStore = true;
      } catch (error) { db.exec('ROLLBACK'); db.close(); throw error; }
    } else {
      const runtime = db.prepare('SELECT * FROM runtime WHERE id=1').get();
      if (runtime.user_id !== seed.user_id || runtime.seed_hash !== hash(JSON.stringify(seed)))
        throw new Error('SQLite profile belongs to another seed');
      state = JSON.parse(db.prepare('SELECT data FROM server_state WHERE id=1').get().data);
      state.tables = Object.fromEntries(db.prepare('SELECT name,data FROM profile').all().map(row => [row.name, JSON.parse(row.data)]));
      if (Object.keys(state.tables).length !== 207) throw new Error('Incomplete SQLite profile');
    }
  } else if (fs.existsSync(statePath)) {
    state = JSON.parse(fs.readFileSync(statePath));
  } else {
    state = structuredClone(initialState ?? freshState()); newStore = true;
  }
  if (!validState(state)) throw new Error('Invalid mobile server state');
  state.tables ??= {};
  state.next_operation_id ??= 1; state.pending_operations ??= {}; state.claims ??= {};
  if (!Number.isSafeInteger(state.next_operation_id) || state.next_operation_id < 1 ||
      !state.pending_operations || Array.isArray(state.pending_operations) || typeof state.pending_operations !== 'object' ||
      !state.claims || Array.isArray(state.claims) || typeof state.claims !== 'object')
    throw new Error('Invalid mobile operation state');
  state.billing ??= { charge: 0, free: 0, subscriptions: {}, orders: {}, transactions: [] };
  state.lottery ??= { draws: 0, used_tickets: {} }; state.lottery.used_tickets ??= {};
  if (![state.billing.charge, state.billing.free].every(Number.isSafeInteger) || state.billing.charge < 0 || state.billing.free < 0 ||
      !state.billing.subscriptions || Array.isArray(state.billing.subscriptions) || !state.billing.orders || Array.isArray(state.billing.orders) ||
      !Array.isArray(state.billing.transactions) || !Number.isSafeInteger(state.lottery.draws) || state.lottery.draws < 0 ||
      !state.lottery.used_tickets || Array.isArray(state.lottery.used_tickets)) throw new Error('Invalid mobile billing state');
  function persist(dirtyTables = []) {
    if (!db) return atomicJson(statePath, state);
    const saved = { ...state }; delete saved.tables;
    db.exec('BEGIN IMMEDIATE');
    try {
      db.prepare('UPDATE server_state SET data=? WHERE id=1').run(JSON.stringify(saved));
      const update = db.prepare('UPDATE profile SET data=?,token=? WHERE name=?');
      for (const name of dirtyTables) {
        const data = JSON.stringify(state.tables[name]);
        if (update.run(data, hash(data, 'md5'), name).changes !== 1) throw new Error('Missing SQLite profile table');
      }
      db.exec('COMMIT');
    } catch (error) { db.exec('ROLLBACK'); throw error; }
  }
  if (newStore && !database) persist();
  const uuidHex = hash(`forevereden-gree:${seed.user_id}`).slice(0, 32);
  const greeUuid = `${uuidHex.slice(0, 8)}-${uuidHex.slice(8, 12)}-${uuidHex.slice(12, 16)}-${uuidHex.slice(16, 20)}-${uuidHex.slice(20)}`;
  const table = (name, overrides = state.tables) => Object.hasOwn(overrides, name) ? overrides[name] : seed.tables[name];
  const tokens = (overrides = state.tables) => {
    const value = Object.fromEntries(Object.keys(seed.tables).map(name => [name, hash(JSON.stringify(table(name, overrides)), 'md5')]));
    for (const [alias, name] of Object.entries(seed.token_aliases)) value[alias] = value[name];
    return value;
  };
  const snapshot = () => ({ ...state, meta: structuredClone(state.meta), billing: structuredClone(state.billing),
    lottery: structuredClone(state.lottery), replies: structuredClone(state.replies),
    pending_operations: structuredClone(state.pending_operations), claims: structuredClone(state.claims) });
  const pendingOperations = () => Object.values(state.pending_operations).sort((a, b) => a.id - b.id);
  function issueOperation(type, parameters) {
    requireValue(Number.isSafeInteger(type) && type > 0 && pendingOperations().length < 128, 'Operation queue exhausted');
    const operation = { id: state.next_operation_id++, type, parameters,
      token: crypto.randomBytes(16).toString('hex'), signature: crypto.randomInt(1, 0x100000000) };
    state.pending_operations[operation.id] = operation;
    return operation;
  }
  function operationGift(row) {
    requireValue(row && Number.isSafeInteger(row.id) && row.id > 0 && row.state === 0 && Array.isArray(row.contents) &&
      row.contents.every(item => Number.isSafeInteger(item.id) && Number.isSafeInteger(item.itemId) && item.itemId > 0 &&
        Number.isSafeInteger(item.amount) && item.amount > 0), 'Gift unavailable');
    return { userId: state.user_id, id: row.id, senderType: row.senderType, senderId: row.senderId,
      title: row.title, message: row.message, contents: row.contents.map(item => ({ id: item.id, itemId: item.itemId,
        amount: item.amount, paramType: item.paramType ?? 0, value: item.value ?? 0 })),
      giftAcquiredType: row.giftAcquiredType, receiveType: row.receiveType, startAt: row.startAt, expireAt: row.expireAt,
      state: row.state, createdAt: row.createdAt, securityToken: row.securityToken ?? '',
      userOdealAchievementId: row.userOdealAchievementId ?? 0 };
  }
  function createStarGift(label, senderId) {
    const source = REWARD_CATALOG.gift_details[label];
    requireValue(source && source.contents.length && source.contents.every(item => Number.isSafeInteger(item.item_id) && item.item_id > 0),
      'Gift contents unavailable');
    if (!Number.isSafeInteger(state.next_gift_id)) {
      const rows = table('UserGift'), gifts = rows ? (Array.isArray(rows) ? rows : [rows]) : [];
      state.next_gift_id = Math.max(0x100000000, ...gifts.map(gift => gift.id).filter(Number.isSafeInteger)) + 1;
    }
    const now = Math.floor(Date.now() / 1000);
    return { userId: state.user_id, id: state.next_gift_id++, senderType: 2, senderId, title: source.title,
      message: source.message, contents: source.contents.map((item, id) => ({ id, itemId: item.item_id, amount: item.amount,
        paramType: 0, value: 0 })), giftAcquiredType: 20, receiveType: 10, startAt: 0, expireAt: 0, state: 0,
      createdAt: now, securityToken: '', userOdealAchievementId: 0 };
  }
  function consumeGems(cost) {
    requireValue(Number.isSafeInteger(cost) && cost >= 0 && state.billing.charge + state.billing.free >= cost,
      'Insufficient Chronos Stones');
    const paid = Math.min(state.billing.charge, cost);
    state.billing.charge -= paid; state.billing.free -= cost - paid;
  }
  function dispatch(req, wire) {
    const before = snapshot();
    try { return dispatchUnsafe(req, wire); } catch (error) { state = before; throw error; }
  }
  function dispatchUnsafe(req, wire) {
    const match = req.url.match(PREFIX);
    requireValue(req.method === 'POST' && match && !req.url.includes('?'), 'Unsupported request target');
    const action = req.url.slice(match[0].length);
    if (!ACTIONS.has(action)) fail(503, `Unsupported operation ${hash(action)}`);
    requireValue((match[1] === 'asset') === (action === 'user/migration/status'), 'Unsupported request namespace');
    requireValue(req.headers.host === '127.0.0.1:28765', 'Host mismatch');
    requireValue(req.headers['x-kms-client-version'] === '3.17.0' && req.headers['x-kms-client-version-code'] === '699', 'Client version mismatch');
    const requestId = req.headers['x-kms-request-id'], sequence = req.headers['x-kms-request-sequence'];
    requireValue(/^[0-9]{1,10}$/.test(requestId ?? '') || requestId === '-1' && BOOTSTRAP.has(action), 'Request ID bound');
    requireValue(/^[0-9]{1,19}$/.test(sequence ?? ''), 'Sequence bound');
    const token = req.headers['x-kms-one-time-token'] ?? '', user = req.headers['x-kms-user'] ?? '', device = req.headers['x-kms-device'] ?? '';
    requireValue(typeof token === 'string' && token.length <= 128 && typeof device === 'string' && device.length <= 1024, 'Header bound');
    const deviceHash = hash(device), bootstrap = BOOTSTRAP.has(action);
    const authenticated = user === String(state.user_id) && token === state.capability && state.device_hash === deviceHash;
    const firstLocalPair = token === '' && ['matching_user/game_user_id','user/game_user_id_for_eu','user/login'].includes(action) &&
      (state.device_hash === null || state.device_hash === deviceHash);
    if (!authenticated && !firstLocalPair) fail(401, 'Local capability required');
    const mode = req.headers['x-kms-encryption'];
    requireValue(mode === '0' || mode === '1', 'Unsupported encryption mode');
    const iv = ['matching_user/game_user_id','user/game_user_id_for_eu','user/login'].includes(action) ? fallbackIV : Buffer.from(state.aes_iv);
    const body = mode === '1' ? decryptBody(wire, key, iv, LIMITS) : wire;
    requireValue(body.length <= LIMITS.plaintext && req.headers['x-kms-request-body-hash'] === hash(body, 'md5'), 'Request checksum mismatch');
    const replayKey = `${requestId}/${sequence}`, bodyHash = hash(body, 'md5'), old = bootstrap ? null : state.replies[replayKey];
    if (old) {
      requireValue(old.action === action && old.body_hash === bodyHash && old.device_hash === deviceHash, 'Conflicting replay');
      return { action, headers: old.headers, body: Buffer.from(old.body, 'base64'), replay: true };
    }
    if (!bootstrap) requireValue(BigInt(sequence) > BigInt(state.last_sequence), 'Stale sequence');
    const allTokens = tokens(); let response, contentType = 'application/json', nextTables = null, dirtyTables = [];
    function empty() { requireValue(body.length === 0, 'Expected empty body'); }
    if (action === 'matching_user/game_user_id' || action === 'user/game_user_id_for_eu') {
      empty(); response = { code: 0, game_user_id: state.user_id, aesIv: state.aes_iv };
    }
    else if (action === 'user/login') {
      empty(); response = { ...seed.login, code: 0, aesIv: state.aes_iv, data: { UserStatus: table('UserStatus') }, dataTokens: { UserStatus: allTokens.UserStatus } };
    } else if (action === 'user/update_meta') {
      const value = JSON.parse(body); requireValue(value && Object.keys(value).length === 1 && [0,1].includes(value.is32bit), 'Unsupported metadata');
      state.meta = value; response = { code: 0 };
    } else if (action === 'user_data/confirm') { empty(); response = { code: 0, dataTokens: allTokens,
      migrators: [], operations: pendingOperations() }; }
    else if (action === 'user/migration/status_reset') { empty(); response = { code: 0 }; }
    else if (action === 'user_data/push') {
      const value = JSON.parse(body);
      log(JSON.stringify({ event: 'private-save-observed', deltas: Array.isArray(value?.deltas) ? value.deltas.length : null,
        triggers: Array.isArray(value?.deltas) ? value.deltas.map(delta => delta?.trigger ?? null) : [],
        put_tables: value?.deltas?.[0]?.putItems && !Array.isArray(value.deltas[0].putItems) ? Object.keys(value.deltas[0].putItems).sort() : [],
        put_counts: value?.deltas?.[0]?.putItems && !Array.isArray(value.deltas[0].putItems) ?
          Object.fromEntries(Object.entries(value.deltas[0].putItems).map(([name, rows]) => [name, Array.isArray(rows) ? rows.length : null])) : {},
        delete_tables: value?.deltas?.[0]?.deleteItems && !Array.isArray(value.deltas[0].deleteItems) ? Object.keys(value.deltas[0].deleteItems).sort() : [],
        token_tables: value?.dataTokens && !Array.isArray(value.dataTokens) ? Object.keys(value.dataTokens).sort() : [],
        operations: Array.isArray(value?.operations) ? value.operations.length : null,
        gifts: Array.isArray(value?.giftIds) ? value.giftIds.length : null, surplus: Array.isArray(value?.surplus) ? value.surplus.length : null }));
      requireValue(sameKeys(value, ['badges','checksums','dataTokens','deltas','giftIds','operations','scripts','surplus']) &&
        Array.isArray(value.deltas) && value.deltas.length <= 32 && Array.isArray(value.giftIds) && value.giftIds.length === 0 &&
        Array.isArray(value.operations) && value.operations.length <= 128 && Array.isArray(value.surplus) && value.surplus.length === 0 &&
        value.deltas.length + value.operations.length > 0,
      'Unsupported save envelope');
      const operationAcks = value.operations.map(item => {
        requireValue(sameKeys(item, ['id','verifier']) && Number.isSafeInteger(item.id) && item.id > 0 &&
          typeof item.verifier === 'string' && item.verifier.length >= 1 && item.verifier.length <= 1024 &&
          state.pending_operations[item.id],
        'Unknown operation acknowledgement');
        return item.id;
      });
      requireValue(new Set(operationAcks).size === operationAcks.length, 'Duplicate operation acknowledgement');
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
      dirtyTables = mutationNames;
      requireValue(mutationNames.every(name => Object.hasOwn(seed.tables, name)) && sameKeys(value.dataTokens, mutationNames) &&
        sameKeys(value.checksums, ['after','before']) && sameKeys(value.checksums.before, mutationNames) &&
        sameKeys(value.checksums.after, mutationNames), 'Unsupported save transaction');
      for (const name of mutationNames) requireValue(/^[0-9a-f]{32}$/.test(value.dataTokens[name]) &&
        value.dataTokens[name] === allTokens[name] && /^[0-9a-f]{32}$/.test(value.checksums.before[name]) &&
        /^[0-9a-f]{32}$/.test(value.checksums.after[name]), 'Invalid save table');
      // ponytail: local single-player compatibility trusts authenticated client deltas; add domain rules before multiplayer.
      nextTables = { ...state.tables };
      const putCounts = {}, deleteCounts = {}, data = {};
      for (const { delta, puts, deletes } of mutations) {
        for (const name of [...puts, ...deletes]) {
          let rows = delta.putItems[name] ?? delta.deleteItems[name]; const current = table(name, nextTables);
          requireValue(Array.isArray(rows) && rows.length >= 1 && rows.length <= Math.max(Array.isArray(current) ? current.length : 1, 4096),
            `Invalid save table ${name}`);
          rows = localRows(rows, state.user_id);
          if (Object.hasOwn(delta.putItems, name)) delta.putItems[name] = rows; else delta.deleteItems[name] = rows;
          mutationKeys(name, current, rows);
        }
        for (const name of puts) {
          const rows = delta.putItems[name], current = table(name, nextTables);
          nextTables[name] = upsert(current, rows, mutationKeys(name, current, rows));
          putCounts[name] = (putCounts[name] ?? 0) + rows.length;
        }
        for (const name of deletes) {
          const rows = delta.deleteItems[name], current = table(name, nextTables);
          nextTables[name] = remove(current, rows, mutationKeys(name, current, rows));
          deleteCounts[name] = (deleteCounts[name] ?? 0) + rows.length;
        }
      }
      const itemTokenCount = (putCounts.UserItemToken ?? 0) + (deleteCounts.UserItemToken ?? 0);
      if (itemTokenCount) data.UserItemToken = Array.from({ length: itemTokenCount }, () =>
        ({ userId: state.user_id, signature: crypto.randomInt(1, 0x80000000) }));
      const randomSeedCount = (putCounts.UserRandomSeed ?? 0) + (deleteCounts.UserRandomSeed ?? 0);
      if (randomSeedCount) data.UserRandomSeed = Array.from({ length: randomSeedCount }, () => ({ userId: state.user_id,
        dynamoDbExpiredAt: Math.floor(Date.now() / 1000) + 86400, seed: crypto.randomInt(1, 0x80000000),
        signature: crypto.randomInt(1, 0x80000000) }));
      const nextTokens = tokens(nextTables);
      const responseTokenNames = [...mutationNames];
      if (mutationNames.includes('UserItemToken')) responseTokenNames.push('ItemTokens');
      if (mutationNames.includes('UserRandomSeed')) responseTokenNames.push('RandomSeeds');
      for (const id of operationAcks) delete state.pending_operations[id];
      response = { code: 0, triggers: mutations.map(item => item.delta.trigger), putItems: putCounts,
        deleteItems: Object.keys(deleteCounts).length ? deleteCounts : [], data,
        operations: pendingOperations(), dones: operationAcks.map(id => ({ id })),
        dataTokens: Object.fromEntries(responseTokenNames.map(name => [name, nextTokens[name]])) };
    } else if (action === 'user_data/pull') {
      const value = JSON.parse(body);
      requireValue(value && Object.keys(value).sort().join(',') === 'consistentRead,recovery,tables' && Array.isArray(value.tables) &&
        typeof value.consistentRead === 'boolean' && value.recovery === false && value.tables.length <= 207 && new Set(value.tables).size === value.tables.length,
      'Unsupported profile pull');
      const data = {}, dataTokens = {};
      for (const name of value.tables) {
        requireValue(typeof name === 'string' && Object.hasOwn(seed.tables, name), 'Unknown profile table');
        data[name] = table(name); dataTokens[name] = allTokens[name];
      }
      for (const [alias, name] of Object.entries(seed.token_aliases)) if (Object.hasOwn(data, name)) dataTokens[alias] = allTokens[alias];
      response = { data, dataTokens, recovery: false }; contentType = seed.pull_content_type ?? 'application/x-msgpack';
    } else if (action === 'battle/continue') {
      empty(); const cost = REWARD_CATALOG.consume.battle_continue; consumeGems(cost);
      response = { code: 0, operations: [issueOperation(4000, {})] };
      log(JSON.stringify({ event: 'private-battle-continue', cost }));
    } else if (action === 'lottery/draw') {
      const value = body.length ? JSON.parse(body) : null;
      requireValue(sameKeys(value, ['id','lotteryPCExId','lotteryPCExIds','lotteryTicketId']) &&
        Number.isSafeInteger(value.id) && value.id > 0 && Number.isSafeInteger(value.lotteryPCExId) && value.lotteryPCExId >= 0 &&
        Array.isArray(value.lotteryPCExIds) && value.lotteryPCExIds.length <= 10 &&
        value.lotteryPCExIds.every(id => Number.isSafeInteger(id) && id > 0) &&
        value.lotteryTicketId === 0, 'Unsupported lottery draw');
      const banner = LOTTERY_CATALOG.banners[value.id];
      requireValue(banner, 'Unknown 3.17.0 lottery banner');
      const [bannerCost, , count, normalCount, normalGroup, guaranteedCount, guaranteedGroup] = banner;
      const cost = bannerCost;
      consumeGems(cost);
      const selectors = [value.lotteryPCExId, ...value.lotteryPCExIds].filter(Boolean);
      const ownedPCs = new Set((table('UserPC') ?? []).map(pc => pc.pcId));
      let selectorIndex = 0;
      const stocks = [];
      for (const [drawCount, group] of [[normalCount, normalGroup], [guaranteedCount, guaranteedGroup]]) {
        if (!drawCount) continue;
        const pool = LOTTERY_CATALOG.pools[group];
        requireValue(Array.isArray(pool) && pool.length > 0, 'Missing 3.17.0 lottery pool');
        const weighted = pool.some(stock => stock[3] > 0);
        for (let index = 0; index < drawCount; index++) {
          if (weighted) stocks.push(weightedStock(pool));
          else {
            const selected = pool.find(stock => stock[0] === selectors[selectorIndex++]);
            requireValue(selected, 'Invalid explicit encounter'); stocks.push(selected);
          }
        }
      }
      requireValue(stocks.length === count, 'Invalid 3.17.0 lottery layout');
      const userPC = stocks.map(stock => ({ stock: { id: stock[0] } }));
      state.lottery.draws += count;
      const parameters = { lotteryId: value.id, drawCount: count, limitedLotteryTickets: [], lotteryTicketId: value.lotteryTicketId, userPC };
      response = { code: 0, ...parameters, operations: [issueOperation(1000, parameters)] };
      log(JSON.stringify({ event: 'private-lottery-draw', lottery_id: value.id, count, cost,
        stock_ids: userPC.map(result => result.stock.id), rarities: stocks.map(stock => stock[2]),
        duplicates: stocks.map(stock => ownedPCs.has(stock[1])) }));
    } else if (Object.hasOwn(CLIENT_SAVE_ACTIONS, action)) {
      const value = JSON.parse(body), keys = CLIENT_SAVE_ACTIONS[action];
      requireValue(sameKeys(value, keys), 'Unsupported action body');
      for (const [name, item] of Object.entries(value)) {
        if (name.endsWith('Ids')) requireValue(Array.isArray(item) &&
          item.length >= (action === 'battle_rush/reward' && name === 'missionIds' ? 0 : 1) && item.length <= 100 &&
          item.every(id => Number.isSafeInteger(id) && id > 0) && new Set(item).size === item.length, 'Invalid action identifiers');
        else if (name === 'userId') requireValue(item === state.user_id, 'User identity mismatch');
        else requireValue(Number.isSafeInteger(item) && item >= 0 && (name === 'slotNo' ? item < 4 : true), 'Invalid action identifier');
      }
      if (action === 'gift/receive') {
        const gifts = table('UserGift'), rows = gifts ? (Array.isArray(gifts) ? gifts : [gifts]) : [];
        const selected = value.giftIds.map(id => rows.find(gift => gift.id === id));
        requireValue(selected.every(Boolean) && !pendingOperations().some(operation => operation.type === 2000 &&
          operation.parameters.UserGift.some(gift => value.giftIds.includes(gift.id))), 'Gift unavailable');
        const operationGifts = selected.map(operationGift);
        state.billing.free += operationGifts.flatMap(gift => gift.contents)
          .reduce((sum, item) => sum + (item.itemId === REWARD_CATALOG.currency_gem_id ? item.amount : 0), 0);
        response = { code: 0, operations: [issueOperation(2000, { UserGift: operationGifts })] };
      } else if (action === 'quest/close') {
        const quests = table('UserQuest') ?? [], quest = quests.find(row => row.questId === value.id);
        const rewards = REWARD_CATALOG.quests[value.id];
        requireValue(quest?.state === 4 && rewards?.length && rewards.every(([id, label, amount]) =>
          Number.isSafeInteger(id) && id > 0 && typeof label === 'string' && label && Number.isSafeInteger(amount) && amount > 0),
        'Quest reward unavailable');
        const parameters = { quest: { id: value.id }, questReward: rewards.map(([id]) => ({ id })) };
        state.billing.free += rewards.reduce((sum, [, label, amount]) => sum + (label === 'currency.gem' ? amount : 0), 0);
        response = { code: 0, operations: [issueOperation(5000, parameters)] };
        log(JSON.stringify({ event: 'private-quest-close', quest_id: value.id, reward_ids: parameters.questReward.map(item => item.id) }));
      } else if (action === 'dungeon/complete') {
        requireValue(REWARD_CATALOG.dungeons.includes(value.dungeonId), 'Dungeon unavailable');
      } else if (action === 'dungeon/ticket/issue') {
        const consume = REWARD_CATALOG.consume.dungeon_tickets[value.id];
        requireValue(consume && value.num >= 1, 'Dungeon ticket unavailable');
        const [unitCost, ticketId, unitAmount] = consume, amount = unitAmount * value.num;
        const rows = table('UserDungeonTicket') ?? [], ticket = rows.find(row => row.dungeonTicketId === ticketId);
        requireValue(Number.isSafeInteger(amount) && amount > 0 && ticket &&
          ticket.amount + amount <= REWARD_CATALOG.dungeon_tickets[ticketId][0], 'Dungeon ticket unavailable');
        consumeGems(unitCost * value.num);
        const parameters = { userDungeonTicket: { dungeonTicketId: ticketId }, gamelibConsume: { acquireAmount: amount } };
        response = { code: 0, ...parameters, operations: [issueOperation(3000, parameters)] };
      } else if (action === 'battle_rush/reward') {
        const stage = REWARD_CATALOG.battle_rush[value.stageId];
        const stages = table('UserBattleRushStage') ?? [], courses = table('UserBattleRushCourse') ?? [];
        const claim = `battle_rush:${value.stageId}`;
        requireValue(stage && stage[0] === value.courseId && stages.some(row => row.battleRushStageId === value.stageId) &&
          courses.some(row => row.battleRushCourseId === value.courseId) && !state.claims[claim] &&
          value.missionIds.every(id => stage[2].some(mission => mission[0] === id)),
          'Battle Rush reward unavailable');
        const GiveItems = [{ itemId: stage[1][1], amount: stage[1][2], missionId: 0, stageId: value.stageId },
          ...value.missionIds.map(id => {
            const mission = stage[2].find(row => row[0] === id);
            return { itemId: mission[2], amount: mission[3], missionId: id, stageId: value.stageId };
          })];
        state.claims[claim] = true;
        state.billing.free += GiveItems.reduce((sum, item) =>
          sum + (item.itemId === REWARD_CATALOG.currency_gem_id ? item.amount : 0), 0);
        response = { code: 0, operations: [issueOperation(18000, { GiveItems })] };
      } else if (action === 'star_library/level_reward') {
        const rows = table('UserStarLibraryLevel') ?? [], gifts = table('UserGift') ?? [];
        requireValue(value.levelIds.every(id => REWARD_CATALOG.star_library.levels[id] &&
          rows.some(row => row.starLibraryLevelId === id && row.state === 1) &&
          !gifts.some(gift => gift.senderType === 2 && gift.senderId === id)) &&
          !pendingOperations().some(operation => operation.type === 22000 &&
            operation.parameters.levelIds.some(id => value.levelIds.includes(id))), 'Star Library level unavailable');
        const UserGift = value.levelIds.map(id => createStarGift(REWARD_CATALOG.star_library.levels[id][0], id));
        response = { code: 0, operations: [issueOperation(22000, { UserGift, levelIds: value.levelIds })] };
      } else if (action === 'star_library/mission_reward') {
        const rows = table('UserStarLibraryMissionStatus') ?? [], gifts = table('UserGift') ?? [];
        requireValue(value.missionIds.every(id => REWARD_CATALOG.star_library.missions[id]?.[0].includes(value.bookId) &&
          rows.some(row => row.missionId === id && row.bookId === value.bookId && [3,4].includes(row.state)) &&
          !gifts.some(gift => gift.senderType === 2 && gift.senderId === id)) &&
          !pendingOperations().some(operation => operation.type === 21000 &&
            operation.parameters.missionIds.some(id => value.missionIds.includes(id))),
          'Star Library mission unavailable');
        const UserGift = value.missionIds.map(id => createStarGift(REWARD_CATALOG.star_library.missions[id][1], id));
        response = { code: 0, operations: [issueOperation(21000, { UserGift, missionIds: value.missionIds })] };
      } else if (action === 'star_library/score_attack_reward') {
        const rows = table('UserStarLibraryScoreAttackReward') ?? [], gifts = table('UserGift') ?? [];
        requireValue(value.scoreAttackRewardIds.every(id => REWARD_CATALOG.star_library.scores[id] &&
          rows.some(row => row.starLibraryScoreAttackRewardId === id && row.state === 1) &&
          !gifts.some(gift => gift.senderType === 2 && gift.senderId === id)) &&
          !pendingOperations().some(operation => operation.type === 23000 &&
            operation.parameters.scoreAttackRewardIds.some(id => value.scoreAttackRewardIds.includes(id))),
          'Star Library score reward unavailable');
        const UserGift = value.scoreAttackRewardIds.map(id => createStarGift(REWARD_CATALOG.star_library.scores[id][0], id));
        response = { code: 0, operations: [issueOperation(23000, { UserGift, scoreAttackRewardIds: value.scoreAttackRewardIds })] };
      } else if (action === 'pack_product/acquire') {
        requireValue(REWARD_CATALOG.pack_products[value.packProductId], 'Pack product unavailable');
      } else if (action === 'pc_costume/acquire') {
        requireValue(REWARD_CATALOG.pc_costume_products[value.pcCostumeProductId], 'Costume product unavailable');
      } else if (action === 'cat_diary/reward') {
        requireValue(Object.values(REWARD_CATALOG.cat_diary).some(reward => reward[2] === value.step), 'Cat Diary reward unavailable');
      }
      if (!response) fail(503, `Untraced action semantics ${hash(action)}`);
      log(JSON.stringify({ event: 'private-client-save-action', action, identifiers: value }));
    } else {
      const value = body.length ? JSON.parse(body) : null;
      requireValue(value === null || typeof value === 'object' && !Array.isArray(value), 'Unsupported action body');
      if (action === 'user/migration/status') response = { code: 0, status: 0 };
      else fail(503, `Untraced action semantics ${hash(action)}`);
      log(JSON.stringify({ event: 'private-action', action, request_bytes: body.length }));
    }
    const plain = contentType === 'application/json' ? Buffer.from(JSON.stringify(response)) : encodeMsgpack(response, LIMITS.plaintext);
    const encoded = encryptBody(plain, key, iv, LIMITS), now = String(Math.floor(Date.now() / 1000));
    const headers = { 'Content-Type': contentType, 'Content-Length': String(encoded.length), 'Cache-Control': 'no-store', Connection: 'close',
      'X-KMS-ENCRYPTION': '1', 'X-KMS-REQUEST-ID': requestId, 'X-KMS-REQUEST-SEQUENCE': sequence,
      'X-KMS-REQUEST-BODY-HASH': bodyHash, 'X-KMS-ONE-TIME-TOKEN': state.capability, 'X-KMS-USER': String(state.user_id),
      'X-KMS-SERVER-RESPONSE-CODE': '0', 'X-KMS-SERVER-TIMESTAMP': now, 'X-KMS-ACCEPT-TIMESTAMP': now,
      'X-KMS-SERVER-VERSION': 'ForeverEden-Android/1', 'X-KMS-WEBSHOP-LINK': '0' };
    state.device_hash = deviceHash;
    if (nextTables) state.tables = nextTables;
    if (!bootstrap) {
      const replies = Object.keys(state.replies);
      if (replies.length >= 1024) delete state.replies[replies[0]];
      state.last_sequence = sequence; state.replies[replayKey] = { action, body_hash: bodyHash, device_hash: deviceHash, headers, body: encoded.toString('base64') };
    }
    persist(dirtyTables);
    return { action, headers, body: encoded, replay: false };
  }
  function dispatchBilling(req, wire) {
    const before = snapshot();
    try { return dispatchBillingUnsafe(req, wire); } catch (error) { state = before; throw error; }
  }
  function dispatchBillingUnsafe(req, wire) {
    requireValue(['127.0.0.1:28765','localhost:28765'].includes(req.headers.host), 'Host mismatch');
    const target = new URL(req.url.replace(/^\/+/, '/'), 'http://127.0.0.1:28765');
    const action = target.pathname;
    requireValue(target.origin === 'http://127.0.0.1:28765' && wire.length <= 64 * 1024, 'Unsupported billing target');
    let response;
    if (req.method === 'POST' && action === '/v1.0/auth/initialize') {
      const value = JSON.parse(wire); requireValue(value && !Array.isArray(value), 'Invalid authorization request');
      response = { result: 'OK', uuid: greeUuid };
    } else if (req.method === 'POST' && action === '/v1.0/auth/authorize') {
      requireValue(wire.length === 0, 'Invalid authorization request'); response = { result: 'OK' };
    } else if (req.method === 'GET' && action === '/v1.0/auth/x_uid') {
      requireValue(wire.length === 0, 'Invalid XUID request');
      response = { result: 'OK', x_uid: `forevereden-${seed.user_id}`, x_app_id: 'anothereden' };
    } else if (req.method === 'POST' && action === '/v1.0/auth/x_uid') {
      const value = JSON.parse(wire); requireValue(typeof value?.x_uid === 'string' && typeof value?.x_app_id === 'string', 'Invalid XUID registration');
      response = { result: 'OK' };
    } else if (req.method === 'POST' && action === '/v1.0/deviceverification/nonce') {
      requireValue(wire.length === 0, 'Invalid nonce request');
      response = { result: 'OK', nonce: Buffer.from(hash(`forevereden-nonce:${seed.user_id}`), 'hex').toString('base64url') };
    } else if (req.method === 'POST' && action === '/v1.0/deviceverification/verify') {
      const value = JSON.parse(wire); requireValue(value && !Array.isArray(value), 'Invalid device verification request');
      response = { result: 'OK', verify_result_code: 0, sf_verify_result_code: 0, integrity_verify_result_code: 0,
        integrity_device_recognition: 'MEETS_DEVICE_INTEGRITY', integrity_app_recognition: 'PLAY_RECOGNIZED',
        integrity_app_licensing: 'LICENSED' };
    } else if (req.method === 'GET' && action === '/v1.0/payment/productlist') {
      requireValue(target.search === '' || target.search === '?develop=1', 'Unsupported billing query');
      response = { result: 'OK', entry: { products: BILLING_PRODUCTS, welcome: 0 } };
    } else if (req.method === 'GET' && action === '/v1.0/payment/subscription/productlist') {
      requireValue(target.search === '' || target.search === '?develop=1', 'Unsupported billing query');
      response = { result: 'OK', entry: { products: [], welcome: 0 } };
    } else if (req.method === 'GET' && action === '/v1.0/payment/balance') {
      requireValue(target.search === '' || /^\?expire_in=\d{1,9}$/.test(target.search), 'Unsupported billing query');
      response = { result: 'OK', entry: { balance_charge_gem: state.billing.charge,
        balance_free_gem: state.billing.free, balance_total_gem: state.billing.charge + state.billing.free } };
    } else if (req.method === 'GET' && action === '/v1.0/payment/subscription/status') {
      requireValue(target.search === '', 'Unsupported billing query');
      response = { result: 'OK', entry: [] };
    } else if (req.method === 'GET' && action === '/v1.0/payment/ticket/status') {
      requireValue(target.search === '', 'Unsupported billing query'); response = { result: 'OK', entry: [] };
    } else if (req.method === 'GET' && action === '/v1.0/payment/purchase/alert/setting') {
      requireValue(target.search === '', 'Unsupported billing query');
      response = { result: 'OK', entry: { purchase_alert: false, threshold_amount: 0 } };
    } else if (req.method === 'GET' && action === '/v1.0/payment/ageverification') {
      requireValue(target.search === '', 'Unsupported billing query');
      response = { result: 'OK', entry: { age_group: 3, birthday: '', limit: 0 } };
    } else if (req.method === 'GET' && (action === '/v1.0/payment/history' || action === '/v1.0/payment/subscription/history')) {
      const offset = Number(target.searchParams.get('offset') ?? 0), limit = Number(target.searchParams.get('limit') ?? 100);
      requireValue(Number.isSafeInteger(offset) && offset >= 0 && Number.isSafeInteger(limit) && limit >= 0 && limit <= 1000,
        'Unsupported billing query');
      response = { result: 'OK', entry: { offset, limit, has_next: false, transactions: [] } };
    } else if (req.method === 'POST' && action === '/v1.0/payment/purchase/alert') {
      const value = JSON.parse(wire); requireValue(BILLING_BY_ID.has(value?.product_id), 'Unknown billing product');
      response = { result: 'OK', entry: { total_amount: 0, threshold_amount: 0, price: 0,
        purchase_alert: false, display_alert: false } };
    } else if (req.method === 'POST' && action === '/v1.0/payment/purchase/alert/setting/update') {
      JSON.parse(wire); response = { result: 'OK' };
    } else if (req.method === 'POST' && action === '/v1.0/payment/purchase') {
      const value = JSON.parse(wire), product = BILLING_BY_ID.get(value?.product_id);
      requireValue(product, 'Unknown billing product');
      const requestKey = hash(`${req.method}\n${req.url}\n${req.headers.authorization ?? ''}\n${wire.toString()}`);
      let order = state.billing.orders[requestKey];
      if (!order) {
        requireValue(Object.keys(state.billing.orders).length < 256, 'Billing order budget exhausted');
        order = { purchase_id: crypto.randomUUID(), product_id: product.product_id, created_at: new Date().toISOString() };
        state.billing.orders[requestKey] = order;
        state.billing.charge += product.charge_gem; state.billing.free += product.free_gem + product.bonus_gem;
        state.billing.transactions.push(order);
        log(JSON.stringify({ event: 'private-billing-grant', product_id: product.product_id, purchase_id: order.purchase_id }));
      }
      response = { result: 'OK', entry: { purchase_id: order.purchase_id, need_caution_for_minors: false }, product_id: product.product_id };
    } else if (req.method === 'POST' && action === '/v1.0/payment/purchase/commit') {
      JSON.parse(wire); response = { result: 'OK' };
    } else fail(503, `Unsupported billing operation ${hash(`${req.method} ${action}`)}`);
    persist();
    const body = Buffer.from(JSON.stringify(response));
    return { action: `billing:${action}`, headers: { 'Content-Type': 'application/json', 'Content-Length': String(body.length),
      'Cache-Control': 'no-store', Connection: 'close' }, body, replay: false };
  }
  const server = http.createServer({ maxHeaderSize: 32768, headersTimeout: 5000, requestTimeout: 10000 }, (req, res) => {
    const resource = resources.get(req.url);
    if (resource && req.method === 'GET' && req.headers.host === '127.0.0.1:28765') {
      res.writeHead(200, { 'Content-Type': 'application/json', 'Content-Length': String(resource.length), Connection: 'close' }); res.end(resource); req.resume(); return;
    }
    const billing = /^\/+v1\.0\//.test(String(req.url ?? '')), length = req.headers['content-length'] ?? (billing ? '0' : '');
    if (req.headers['transfer-encoding'] || !/^[0-9]{1,7}$/.test(length) || Number(length) > LIMITS.ciphertext) {
      req.resume(); res.writeHead(413, { Connection: 'close', 'Content-Length': '0' }); return res.end();
    }
    const chunks = []; let size = 0;
    req.on('data', chunk => { size += chunk.length; if (size > LIMITS.ciphertext) req.destroy(); else chunks.push(chunk); });
    req.on('error', () => {});
    req.on('end', () => {
      try {
        requireValue(size === Number(length), 'Request length mismatch');
        const result = billing ? dispatchBilling(req, Buffer.concat(chunks, size)) : dispatch(req, Buffer.concat(chunks, size));
        const send = () => {
          res.writeHead(200, result.headers); res.end(result.body);
          log(JSON.stringify({ event: billing ? 'private-billing-response' : 'private-response', action: result.action,
            request_id: req.headers['x-kms-request-id'] ?? null, sequence: req.headers['x-kms-request-sequence'] ?? null,
            request_bytes: size, response_bytes: result.body.length, replay: result.replay }));
        };
        send();
      } catch (error) {
        const status = error.status ?? (error instanceof SyntaxError || error instanceof RangeError ? 400 : 503);
        const match = req.url?.match(PREFIX);
        log(JSON.stringify({ event: billing ? 'private-billing-rejected' : 'private-rejected', action: billing ? req.url?.split('?', 1)[0] : match ? req.url.slice(match[0].length) : null,
          request_id: req.headers['x-kms-request-id'] ?? null, sequence: req.headers['x-kms-request-sequence'] ?? null,
          status, reason: error.status ? error.message : error.name }));
        res.writeHead(status, { Connection: 'close', 'Content-Length': '0', 'Cache-Control': 'no-store' }); res.end();
      }
    });
  });
  server.maxConnections = 8; server.maxHeadersCount = 64; server.keepAliveTimeout = 1000;
  return { server, state: () => state, close: () => new Promise((resolve, reject) => server.close(error => {
    if (db) db.close(); if (error) reject(error); else resolve();
  })) };
}

function loadResourceDirectory(directory, generation) {
  const resources = new Map();
  for (let phase = 1; phase <= 16; phase++) for (const kind of ['project','version']) {
    const file = path.join(directory, `${kind}.manifest.${phase}.json`);
    const body = fs.readFileSync(file);
    resources.set(`/content/${generation}/${kind}.manifest.${phase}`, body);
  }
  return resources;
}

module.exports = { ACTIONS, SEMANTIC_ROUTES, BILLING_PRODUCTS, LOTTERY_CATALOG, weightedStock,
  REWARD_CATALOG, createMobileServer, loadResourceDirectory };
