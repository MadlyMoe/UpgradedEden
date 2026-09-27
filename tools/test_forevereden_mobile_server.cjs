'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { encryptBody, decryptBody, decodeMsgpack } = require('./forevereden_transport.cjs');
const { ACTIONS, SEMANTIC_ROUTES, BILLING_PRODUCTS, LOTTERY_CATALOG, weightedStock,
  REWARD_CATALOG, createMobileServer } = require('./forevereden_mobile_server.cjs');

const root = path.resolve(__dirname, '..');
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'forevereden/local-runtime-identity.json'))), identity = manifest.identity;
const inventory = JSON.parse(fs.readFileSync(path.join(root, 'data/forevereden-evidence/network-action-inventory.json')));
const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === 'object'
  ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value;
assert.equal(manifest.runtime_id, crypto.createHash('sha256').update(JSON.stringify(canonical(identity))).digest('hex'));
for (const files of [identity.active_server, identity.launcher_source]) for (const [file, digest] of Object.entries(files))
  assert.equal(crypto.createHash('sha256').update(fs.readFileSync(path.join(root, file))).digest('hex'), digest, file);
assert.deepEqual([...ACTIONS].sort(), identity.routed_routes.sort());
assert.deepEqual([...SEMANTIC_ROUTES].sort(), identity.non_stub_routes.sort());
assert.deepEqual([...ACTIONS].filter(action => !SEMANTIC_ROUTES.has(action) &&
  inventory.actions.find(row => row.action === action)?.requirement === 'required_gameplay').sort(),
identity.required_untraced_routes.sort());
const seed = JSON.parse(fs.readFileSync(path.join(root, identity.seed.path)));
for (const [group, rarity] of [[176007885, 3], [176007885, 4], [176007886, 5]]) {
  const stock = LOTTERY_CATALOG.pools[group].find(item => item[2] === rarity && item[3] > 0);
  if (!seed.tables.UserPC.some(pc => pc.pcId === stock[1]))
    seed.tables.UserPC.push({ ...seed.tables.UserPC[0], _id: `lottery-test-${rarity}`, pcId: stock[1], destinyPoint: 0 });
}
const codec = JSON.parse(fs.readFileSync(path.join(root, identity.codec.path)));
assert.deepEqual([...ACTIONS].sort(), inventory.actions.filter(value => value.local_support === 'routed').map(value => value.action).sort());
assert.equal(Object.keys(LOTTERY_CATALOG.banners).length, 3352);
assert.equal(REWARD_CATALOG.source_sha256, '18c811dabc2a3184c81155a54a234dce64ab23e2eebac4ae1cdfde2ee76386eb');
assert.equal(Object.keys(REWARD_CATALOG.gifts).length, 3369);
assert.equal(REWARD_CATALOG.consume.battle_continue, 50);
assert.deepEqual(REWARD_CATALOG.consume.dungeon_tickets['81200101'], [40, 564000001, 2]);
let drawableBanners = 0;
for (const [id, banner] of Object.entries(LOTTERY_CATALOG.banners)) {
  assert.equal(banner[3] + banner[5], banner[2], id);
  if (!banner[4]) { assert.equal(banner[6], 0, id); continue; }
  drawableBanners++;
  assert.ok(LOTTERY_CATALOG.pools[banner[4]]?.length, id);
  if (banner[5]) assert.ok(LOTTERY_CATALOG.pools[banner[6]]?.length, id);
}
assert.equal(drawableBanners, 1682);
const key = Buffer.from(codec.key_hex, 'hex'), fallbackIV = Buffer.from(codec.fallback_iv_hex, 'hex');
const limits = { plaintext: 8 * 1024 * 1024, ciphertext: 4 * 1024 * 1024 };
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'forevereden-mobile-')), statePath = path.join(temp, 'state.json');
let user = '', token = '', iv = fallbackIV, requestId = -1, sequence = 0;

function md5(body) { return crypto.createHash('md5').update(body).digest('hex'); }
function setIdentity(value) {
  if (Array.isArray(value)) return value.forEach(setIdentity);
  if (!value || typeof value !== 'object') return;
  for (const [key, item] of Object.entries(value)) if (key === 'userId') value[key] = seed.user_id; else setIdentity(item);
}
function call(port, action, plain = Buffer.alloc(0), encrypted = false, queued = false, namespace = 'game_client') {
  if (queued) { requestId++; sequence++; }
  const wire = encrypted ? encryptBody(plain, key, iv, limits) : plain;
  const headers = { Host: '127.0.0.1:28765', 'Content-Length': String(wire.length),
    'X-KMS-CLIENT-VERSION': '3.17.0', 'X-KMS-CLIENT-VERSION-CODE': '699',
    'X-KMS-REQUEST-ID': String(requestId), 'X-KMS-REQUEST-SEQUENCE': String(sequence),
    'X-KMS-ONE-TIME-TOKEN': token, 'X-KMS-USER': user, 'X-KMS-DEVICE': 'android-test',
    'X-KMS-ENCRYPTION': encrypted ? '1' : '0', 'X-KMS-REQUEST-BODY-HASH': md5(plain) };
  return new Promise((resolve, reject) => {
    const req = http.request({ hostname: '127.0.0.1', port, method: 'POST', path: `/ap/private/${namespace}/${action}`, headers }, res => {
      const chunks = []; res.on('data', value => chunks.push(value)); res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, body: Buffer.concat(chunks) }));
    });
    req.on('error', reject); req.end(wire);
  });
}
async function listen(app) { await new Promise(resolve => app.server.listen(0, '127.0.0.1', resolve)); return app.server.address().port; }
function billingCall(port, method, route, value = null, authorization = 'OAuth local-test') {
  const body = value === null ? Buffer.alloc(0) : Buffer.from(JSON.stringify(value));
  return new Promise((resolve, reject) => {
    const req = http.request({ hostname: '127.0.0.1', port, method, path: route, headers: {
      Host: '127.0.0.1:28765', Authorization: authorization, 'Content-Length': String(body.length),
    } }, res => {
      const chunks = []; res.on('data', chunk => chunks.push(chunk));
      res.on('end', () => { const body = Buffer.concat(chunks); resolve({ status: res.statusCode, value: body.length ? JSON.parse(body) : null }); });
    });
    req.on('error', reject); req.end(body);
  });
}

(async () => {
  let app = createMobileServer({ seed, codec, statePath, log: () => {} }), port = await listen(app);
  let billed = await billingCall(port, 'POST', '/v1.0/auth/initialize', { device_id: 'android-test', token: 'local-key' });
  assert.equal(billed.status, 200); assert.match(billed.value.uuid, /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/);
  billed = await billingCall(port, 'POST', '/v1.0/auth/authorize'); assert.equal(billed.value.result, 'OK');
  billed = await billingCall(port, 'GET', '/v1.0/auth/x_uid');
  assert.deepEqual({ x_uid: billed.value.x_uid, x_app_id: billed.value.x_app_id }, { x_uid: `forevereden-${seed.user_id}`, x_app_id: 'anothereden' });
  billed = await billingCall(port, 'POST', '/v1.0/deviceverification/nonce');
  assert.equal(billed.value.result, 'OK'); assert.ok(billed.value.nonce.length >= 16);
  billed = await billingCall(port, 'POST', '/v1.0/deviceverification/verify', { emulator: true, integrity_error: 'local' });
  assert.deepEqual([billed.value.verify_result_code, billed.value.sf_verify_result_code, billed.value.integrity_verify_result_code], [0, 0, 0]);
  const [products, subscriptions] = await Promise.all([
    billingCall(port, 'GET', '///////v1.0/payment/productlist?develop=1'),
    billingCall(port, 'GET', '/v1.0/payment/subscription/productlist'),
  ]);
  assert.equal(products.status, 200); assert.deepEqual(products.value.entry.products, BILLING_PRODUCTS);
  assert.deepEqual(subscriptions.value.entry.products, []);
  assert.ok(BILLING_PRODUCTS.every(product => Number(product.price) > 0));
  const stoneBody = { product_id: BILLING_PRODUCTS[0].product_id, country_code: 'US', currency_code: 'USD', price: '0' };
  const firstOrder = await billingCall(port, 'POST', '/v1.0/payment/purchase', stoneBody);
  const replayOrder = await billingCall(port, 'POST', '/v1.0/payment/purchase', stoneBody);
  assert.equal(firstOrder.value.entry.purchase_id, replayOrder.value.entry.purchase_id);
  billed = await billingCall(port, 'GET', '/v1.0/payment/balance');
  assert.deepEqual(billed.value.entry, { balance_charge_gem: 25, balance_free_gem: 5, balance_total_gem: 30 });
  billed = await billingCall(port, 'GET', '/v1.0/payment/subscription/status');
  assert.deepEqual(billed.value.entry, []);
  billed = await billingCall(port, 'POST', '/v1.0/payment/subscription/purchase',
    { product_id: 'games.wfs.anothereden.subscription.daichi' });
  assert.equal(billed.status, 503);
  let response = await call(port, 'matching_user/game_user_id');
  assert.equal(response.status, 200);
  let value = JSON.parse(decryptBody(response.body, key, fallbackIV, limits));
  user = String(value.game_user_id); iv = Buffer.from(value.aesIv);
  response = await call(port, 'user/game_user_id_for_eu');
  assert.equal(JSON.parse(decryptBody(response.body, key, fallbackIV, limits)).game_user_id, seed.user_id);
  response = await call(port, 'user/login');
  assert.equal(JSON.parse(decryptBody(response.body, key, fallbackIV, limits)).code, 0);
  token = response.headers['x-kms-one-time-token'];
  response = await call(port, 'user/update_meta', Buffer.from('{"is32bit":0}'), true);
  assert.equal(JSON.parse(decryptBody(response.body, key, iv, limits)).code, 0);
  response = await call(port, 'user_data/confirm', Buffer.alloc(0), true, true);
  assert.equal(JSON.parse(decryptBody(response.body, key, iv, limits)).code, 0);
  const pullBody = Buffer.from(JSON.stringify({ tables: Object.keys(seed.tables), consistentRead: false, recovery: false }));
  response = await call(port, 'user_data/pull', pullBody, true, true);
  assert.equal(response.status, 200);
  value = decodeMsgpack(decryptBody(response.body, key, iv, limits));
  assert.equal(value.data.UserInfo.userId, seed.user_id);
  const replay = { requestId, sequence, response: Buffer.from(response.body) };
  await new Promise(resolve => app.server.close(resolve));

  app = createMobileServer({ seed, codec, statePath, log: () => {} }); port = await listen(app);
  billed = await billingCall(port, 'GET', '/v1.0/payment/balance');
  assert.equal(billed.value.entry.balance_total_gem, 30);
  billed = await billingCall(port, 'GET', '/v1.0/payment/subscription/status');
  assert.deepEqual(billed.value.entry, []);
  requestId = replay.requestId - 1; sequence = replay.sequence - 1;
  response = await call(port, 'user_data/pull', pullBody, true, true);
  assert.deepEqual(response.body, replay.response);
  const untracedActions = [...ACTIONS].filter(action => !SEMANTIC_ROUTES.has(action));
  const clientSaveBodies = {
    'battle_rush/reward': { stageId: 481000001, courseId: 480000001, missionIds: [483000001] },
    'cat_diary/reward': { lotteryDt: 1, slotNo: 0, step: 1 }, 'dungeon/complete': { dungeonId: 562000031 },
    'dungeon/ticket/issue': { id: 564000001, num: 1 }, 'gift/receive': { userId: seed.user_id, giftIds: [seed.tables.UserGift[0].id] },
    'pack_product/acquire': { packProductId: 2157000001 }, 'pc_costume/acquire': { pcCostumeProductId: 155000001 },
    'quest/close': { id: seed.tables.UserQuest[0].questId }, 'star_library/level_reward': { levelIds: [1] },
    'star_library/mission_reward': { missionIds: [2104000001], bookId: 2101001001 },
    'star_library/score_attack_reward': { scoreAttackRewardIds: [2112000001] },
  };
  clientSaveBodies['star_library/level_reward'].levelIds = [2106000001];
  for (const action of untracedActions) {
    response = await call(port, action, Buffer.from(JSON.stringify(clientSaveBodies[action] ?? {})), true, true,
      action === 'user/migration/status' ? 'asset' : 'game_client');
    assert.equal(response.status, 503, action);
  }
  response = await call(port, 'user/migration/status', Buffer.from('{}'), true, true, 'asset');
  assert.equal(response.status, 200);
  value = JSON.parse(decryptBody(response.body, key, iv, limits));
  assert.deepEqual(value, { code: 0, status: 0 });
  const questId = 621020004, quests = structuredClone(seed.tables.UserQuest);
  quests.push({ ...quests[0], _id: 'quest-close-test', questId, state: 4, questSteps: [] });
  app.state().tables.UserQuest = quests;
  billed = await billingCall(port, 'GET', '/v1.0/payment/balance');
  const beforeQuestGems = billed.value.entry.balance_total_gem;
  const questClose = Buffer.from(JSON.stringify({ id: questId }));
  response = await call(port, 'quest/close', questClose, true, true);
  assert.equal(response.status, 200);
  value = JSON.parse(decryptBody(response.body, key, iv, limits));
  assert.equal(value.data.UserQuest.find(quest => quest.questId === questId).state, 5);
  assert.equal(value.dataTokens.UserQuest, md5(Buffer.from(JSON.stringify(value.data.UserQuest))));
  assert.equal(app.state().tables.UserQuest.find(quest => quest.questId === questId).state, 5);
  const questReplay = { requestId, sequence, response: Buffer.from(response.body) };
  await new Promise(resolve => app.server.close(resolve));
  app = createMobileServer({ seed, codec, statePath, log: () => {} }); port = await listen(app);
  requestId = questReplay.requestId - 1; sequence = questReplay.sequence - 1;
  response = await call(port, 'quest/close', questClose, true, true);
  assert.deepEqual(response.body, questReplay.response);
  billed = await billingCall(port, 'GET', '/v1.0/payment/balance');
  assert.equal(billed.value.entry.balance_total_gem, beforeQuestGems + 5);
  response = await call(port, 'quest/close', questClose, true, true);
  assert.equal(response.status, 400);
  billed = await billingCall(port, 'GET', '/v1.0/payment/balance');
  assert.equal(billed.value.entry.balance_total_gem, beforeQuestGems + 5);
  response = await call(port, 'battle/continue', Buffer.alloc(0), true, true);
  assert.equal(response.status, 400);
  billed = await billingCall(port, 'GET', '/v1.0/payment/balance');
  assert.equal(billed.value.entry.balance_total_gem, 35);
  await billingCall(port, 'POST', '/v1.0/payment/purchase', { product_id: BILLING_PRODUCTS[1].product_id });
  response = await call(port, 'battle/continue', Buffer.alloc(0), true, true);
  assert.equal(response.status, 200);
  const continueReplay = Buffer.from(response.body); requestId--; sequence--;
  response = await call(port, 'battle/continue', Buffer.alloc(0), true, true);
  assert.deepEqual(response.body, continueReplay);
  billed = await billingCall(port, 'GET', '/v1.0/payment/balance');
  assert.equal(billed.value.entry.balance_total_gem, 140);
  const tickets = structuredClone(seed.tables.UserDungeonTicket);
  tickets.find(ticket => ticket.dungeonTicketId === 564000001).amount = 7;
  app.state().tables.UserDungeonTicket = tickets;
  const ticketIssue = Buffer.from(JSON.stringify({ id: 81200101, num: 1 }));
  response = await call(port, 'dungeon/ticket/issue', ticketIssue, true, true);
  assert.equal(response.status, 200);
  value = JSON.parse(decryptBody(response.body, key, iv, limits));
  assert.deepEqual(value, { code: 0, userDungeonTicket: { dungeonTicketId: 564000001 },
    gamelibConsume: { acquireAmount: 2 } });
  assert.equal(app.state().tables.UserDungeonTicket.find(ticket => ticket.dungeonTicketId === 564000001).amount, 9);
  const issueReplay = Buffer.from(response.body); requestId--; sequence--;
  response = await call(port, 'dungeon/ticket/issue', ticketIssue, true, true);
  assert.deepEqual(response.body, issueReplay);
  billed = await billingCall(port, 'GET', '/v1.0/payment/balance');
  assert.equal(billed.value.entry.balance_total_gem, 100);
  response = await call(port, 'gift/receive', Buffer.from(JSON.stringify({ userId: seed.user_id + 1,
    giftIds: [seed.tables.UserGift[0].id] })), true, true);
  assert.equal(response.status, 400);
  response = await call(port, 'pack_product/acquire', Buffer.from(JSON.stringify({ packProductId: 1 })), true, true);
  assert.equal(response.status, 400);
  await billingCall(port, 'POST', '/v1.0/payment/purchase', { product_id: BILLING_PRODUCTS[5].product_id });
  const draw = Buffer.from(JSON.stringify({ id: 175993342, lotteryPCExId: 0, lotteryPCExIds: [], lotteryTicketId: 0 }));
  const banner = LOTTERY_CATALOG.banners['175993342'];
  assert.deepEqual(banner, [1000, 3, 10, 9, 176007885, 1, 176007886]);
  const normalPool = LOTTERY_CATALOG.pools[String(banner[4])], guaranteedPool = LOTTERY_CATALOG.pools[String(banner[6])];
  const rates = pool => Object.fromEntries([3,4,5].map(rarity =>
    [rarity, pool.filter(stock => stock[2] === rarity).reduce((sum, stock) => sum + stock[3], 0)]).filter(([, rate]) => rate));
  assert.deepEqual(rates(normalPool), { 3: 76300, 4: 20400, 5: 3300 });
  assert.deepEqual(rates(guaranteedPool), { 5: 100000 });
  assert.ok(normalPool.includes(weightedStock(normalPool)));
  response = await call(port, 'lottery/draw', draw, true, true);
  assert.equal(response.status, 200);
  const drawReplay = Buffer.from(response.body), drawRequestId = requestId, drawSequence = sequence;
  value = JSON.parse(decryptBody(response.body, key, iv, limits));
  assert.equal(value.userPC.length, 10);
  assert.ok(value.userPC.slice(0, 9).every(item => normalPool.some(stock => stock[0] === item.stock.id)));
  assert.ok(guaranteedPool.some(stock => stock[0] === value.userPC[9].stock.id));
  assert.ok(value.userPC.every(item => item.stock.id > 0x7fffffff));
  billed = await billingCall(port, 'GET', '/v1.0/payment/balance');
  assert.equal(billed.value.entry.balance_total_gem, 2600);
  requestId--; sequence--;
  response = await call(port, 'lottery/draw', draw, true, true);
  assert.equal(response.status, 200); assert.equal(requestId, drawRequestId); assert.equal(sequence, drawSequence);
  assert.deepEqual(response.body, drawReplay);
  billed = await billingCall(port, 'GET', '/v1.0/payment/balance');
  assert.equal(billed.value.entry.balance_total_gem, 2600);
  const ticketDraw = Buffer.from(JSON.stringify({ id: 175993342, lotteryPCExId: 0, lotteryPCExIds: [], lotteryTicketId: 177000002 }));
  response = await call(port, 'lottery/draw', ticketDraw, true, true);
  assert.equal(response.status, 200);
  const ticketReplay = Buffer.from(response.body); requestId--; sequence--;
  response = await call(port, 'lottery/draw', ticketDraw, true, true);
  assert.deepEqual(response.body, ticketReplay);
  response = await call(port, 'lottery/draw', ticketDraw, true, true);
  assert.equal(response.status, 400);
  response = await call(port, 'user_data/confirm', Buffer.alloc(0), true, true);
  const drawTokens = JSON.parse(decryptBody(response.body, key, iv, limits)).dataTokens;
  const saveValue = JSON.parse(fs.readFileSync(path.join(root, 'data/forevereden-evidence/private-login/first-gameplay-push-request-2d385cd2462bf45f.json')));
  saveValue.deltas[0].trigger = 'ExplorerScheduled';
  const save = Buffer.from(JSON.stringify(saveValue));
  response = await call(port, 'user_data/push', save, true, true);
  assert.equal(response.status, 200);
  value = JSON.parse(decryptBody(response.body, key, iv, limits));
  assert.deepEqual(value.triggers, ['ExplorerScheduled']);
  assert.deepEqual(value.putItems, { UserEnvironmentChangeGroup: 1, UserInfo: 1, UserMigratoryEnemy: 1 });
  const migratoryToken = value.dataTokens.UserMigratoryEnemy;
  const nextSave = structuredClone(saveValue);
  delete nextSave.deltas[0].putItems.UserMigratoryEnemy;
  delete nextSave.checksums.before.UserMigratoryEnemy; delete nextSave.checksums.after.UserMigratoryEnemy;
  delete nextSave.dataTokens.UserMigratoryEnemy;
  nextSave.dataTokens = Object.fromEntries(Object.keys(nextSave.dataTokens).map(name => [name, value.dataTokens[name]]));
  nextSave.deltas[0].putItems.UserInfo[0].totalPlayingTime++;
  const nextSaveBody = Buffer.from(JSON.stringify(nextSave));
  response = await call(port, 'user_data/push', nextSaveBody, true, true);
  assert.equal(response.status, 200);
  value = JSON.parse(decryptBody(response.body, key, iv, limits));
  assert.deepEqual(value.putItems, { UserEnvironmentChangeGroup: 1, UserInfo: 1 });
  const environmentToken = value.dataTokens.UserEnvironmentChangeGroup;
  const migratedSave = structuredClone(saveValue);
  delete migratedSave.deltas[0].putItems.UserEnvironmentChangeGroup;
  delete migratedSave.checksums.before.UserEnvironmentChangeGroup; delete migratedSave.checksums.after.UserEnvironmentChangeGroup;
  delete migratedSave.dataTokens.UserEnvironmentChangeGroup;
  migratedSave.dataTokens = Object.fromEntries(Object.keys(migratedSave.dataTokens).map(name =>
    [name, name === 'UserMigratoryEnemy' ? migratoryToken : value.dataTokens[name]]));
  migratedSave.deltas[0].putItems.UserInfo[0].totalPlayingTime += 2;
  response = await call(port, 'user_data/push', Buffer.from(JSON.stringify(migratedSave)), true, true);
  assert.equal(response.status, 200);
  value = JSON.parse(decryptBody(response.body, key, iv, limits));
  assert.deepEqual(value.putItems, { UserInfo: 1, UserMigratoryEnemy: 1 });
  const ticketSave = structuredClone(saveValue);
  ticketSave.deltas[0].putItems.UserDungeonTicket = structuredClone(seed.tables.UserDungeonTicket);
  ticketSave.dataTokens = {
    UserDungeonTicket: md5(Buffer.from(JSON.stringify(seed.tables.UserDungeonTicket))),
    UserEnvironmentChangeGroup: environmentToken,
    UserInfo: value.dataTokens.UserInfo,
    UserMigratoryEnemy: value.dataTokens.UserMigratoryEnemy,
  };
  ticketSave.checksums.before.UserDungeonTicket = '0'.repeat(32);
  ticketSave.checksums.after.UserDungeonTicket = '0'.repeat(32);
  ticketSave.deltas[0].putItems.UserInfo[0].totalPlayingTime += 3;
  response = await call(port, 'user_data/push', Buffer.from(JSON.stringify(ticketSave)), true, true);
  assert.equal(response.status, 200);
  value = JSON.parse(decryptBody(response.body, key, iv, limits));
  assert.deepEqual(value.putItems, { UserDungeonTicket: 8, UserEnvironmentChangeGroup: 1, UserInfo: 1, UserMigratoryEnemy: 1 });
  const areaSave = JSON.parse(fs.readFileSync(path.join(root, 'data/forevereden-evidence/official-login/20260926T065843Z/045-request-plaintext.bin')));
  setIdentity(areaSave);
  areaSave.deltas[0].putItems.UserInfo[0].userId = seed.user_id + 1;
  areaSave.deltas[0].putItems.UserMigratoryEnemy = structuredClone(ticketSave.deltas[0].putItems.UserMigratoryEnemy);
  areaSave.dataTokens = {
    UserGlobalFlag: md5(Buffer.from(JSON.stringify(seed.tables.UserGlobalFlag))), UserInfo: value.dataTokens.UserInfo,
    UserMigratoryEnemy: value.dataTokens.UserMigratoryEnemy, UserSystemFlag: md5(Buffer.from(JSON.stringify(seed.tables.UserSystemFlag))),
  };
  areaSave.checksums.before.UserMigratoryEnemy = ticketSave.checksums.before.UserMigratoryEnemy;
  areaSave.checksums.after.UserMigratoryEnemy = ticketSave.checksums.after.UserMigratoryEnemy;
  response = await call(port, 'user_data/push', Buffer.from(JSON.stringify(areaSave)), true, true);
  assert.equal(response.status, 200);
  value = JSON.parse(decryptBody(response.body, key, iv, limits));
  assert.deepEqual(value.putItems, { UserGlobalFlag: 19, UserInfo: 1, UserMigratoryEnemy: 1, UserSystemFlag: 2 });
  const eventSave = structuredClone(areaSave), eventTables = ['UserAreaEnemy','UserGameManual','UserInfo','UserMigratoryEnemy',
    'UserOrdealAchievementStock','UserPC','UserPCJobSet','UserPCStyle','UserStoryStep','UserSystemFlag'];
  eventSave.deltas[0].trigger = 'EventDone'; eventSave.deltas[0].putItems = {};
  eventSave.dataTokens = {}; eventSave.checksums = { before: {}, after: {} };
  const emptyRows = { UserOrdealAchievementStock: [{ userId: seed.user_id, id: 1 }],
    UserStoryStep: [{ userId: seed.user_id, storyStepId: 1, state: 1 }] };
  for (const name of eventTables) {
    eventSave.deltas[0].putItems[name] = structuredClone(emptyRows[name] ?? (Array.isArray(seed.tables[name]) ? seed.tables[name] : [seed.tables[name]]));
    eventSave.dataTokens[name] = value.dataTokens[name] ?? drawTokens[name];
    eventSave.checksums.before[name] = '0'.repeat(32); eventSave.checksums.after[name] = '0'.repeat(32);
  }
  response = await call(port, 'user_data/push', Buffer.from(JSON.stringify(eventSave)), true, true);
  assert.equal(response.status, 200);
  value = JSON.parse(decryptBody(response.body, key, iv, limits));
  assert.deepEqual(value.putItems, Object.fromEntries(eventTables.sort().map(name => [name,
    eventSave.deltas[0].putItems[name].length])));
  const eventInfoToken = value.dataTokens.UserInfo;
  const freezeSave = structuredClone(eventSave), freezeRow = { userId: seed.user_id, frozenAt: 1 };
  freezeSave.deltas[0].trigger = 'Freezed'; freezeSave.deltas[0].putItems = { UserFreeze: [freezeRow] };
  freezeSave.dataTokens = { UserFreeze: md5(Buffer.from(JSON.stringify(seed.tables.UserFreeze))) };
  freezeSave.checksums = { before: { UserFreeze: '0'.repeat(32) }, after: { UserFreeze: '0'.repeat(32) } };
  response = await call(port, 'user_data/push', Buffer.from(JSON.stringify(freezeSave)), true, true);
  assert.equal(response.status, 200);
  value = JSON.parse(decryptBody(response.body, key, iv, limits));
  assert.deepEqual(value.putItems, { UserFreeze: 1 });
  const treasureSave = structuredClone(freezeSave), mutationTables = ['UserInfo','UserItemToken','UserMaterial','UserRandomSeed','UserTreasure'];
  treasureSave.deltas[0].trigger = 'TreasureGet';
  treasureSave.deltas[0].putItems = { UserInfo: structuredClone(eventSave.deltas[0].putItems.UserInfo),
    UserMaterial: [{ userId: seed.user_id, materialId: 1, amount: 1 }],
    UserTreasure: [{ userId: seed.user_id, treasureId: 1, state: 1 }] };
  treasureSave.deltas[0].deleteItems = { UserItemToken: [structuredClone(seed.tables.UserItemToken[0])],
    UserRandomSeed: [structuredClone(seed.tables.UserRandomSeed[0])] };
  treasureSave.dataTokens = Object.fromEntries(mutationTables.map(name => [name,
    name === 'UserInfo' ? eventInfoToken : md5(Buffer.from(JSON.stringify(seed.tables[name])))]));
  treasureSave.checksums = { before: {}, after: {} };
  for (const name of mutationTables) {
    treasureSave.checksums.before[name] = '0'.repeat(32); treasureSave.checksums.after[name] = '0'.repeat(32);
  }
  response = await call(port, 'user_data/push', Buffer.from(JSON.stringify(treasureSave)), true, true);
  assert.equal(response.status, 200);
  value = JSON.parse(decryptBody(response.body, key, iv, limits));
  assert.deepEqual(value.putItems, { UserInfo: 1, UserMaterial: 1, UserTreasure: 1 });
  assert.deepEqual(value.deleteItems, { UserItemToken: 1, UserRandomSeed: 1 });
  const treasureTokens = value.dataTokens;
  const uiSave = structuredClone(treasureSave);
  uiSave.deltas[0].trigger = 'UiClosed'; uiSave.deltas[0].deleteItems = {};
  uiSave.deltas[0].putItems = { UserEquipmentSpecie: [structuredClone(seed.tables.UserEquipmentSpecie[0])],
    UserInfo: structuredClone(treasureSave.deltas[0].putItems.UserInfo) };
  uiSave.dataTokens = { UserEquipmentSpecie: md5(Buffer.from(JSON.stringify(seed.tables.UserEquipmentSpecie))),
    UserInfo: value.dataTokens.UserInfo };
  uiSave.checksums = { before: { UserEquipmentSpecie: '0'.repeat(32), UserInfo: '0'.repeat(32) },
    after: { UserEquipmentSpecie: '0'.repeat(32), UserInfo: '0'.repeat(32) } };
  response = await call(port, 'user_data/push', Buffer.from(JSON.stringify(uiSave)), true, true);
  assert.equal(response.status, 200);
  value = JSON.parse(decryptBody(response.body, key, iv, limits));
  assert.deepEqual(value.putItems, { UserEquipmentSpecie: 1, UserInfo: 1 });
  const blockingSave = structuredClone(uiSave), blockingTables = ['UserItemToken','UserRandomSeed'];
  blockingSave.deltas[0].trigger = 'Blocking'; blockingSave.deltas[0].deleteItems = {};
  blockingSave.deltas[0].putItems = Object.fromEntries(blockingTables.map(name => [name, [structuredClone(seed.tables[name][0])]]));
  blockingSave.dataTokens = Object.fromEntries(blockingTables.map(name => [name, treasureTokens[name]]));
  blockingSave.checksums = { before: {}, after: {} };
  for (const name of blockingTables) {
    blockingSave.checksums.before[name] = '0'.repeat(32); blockingSave.checksums.after[name] = '0'.repeat(32);
  }
  response = await call(port, 'user_data/push', Buffer.from(JSON.stringify(blockingSave)), true, true);
  assert.equal(response.status, 200);
  value = JSON.parse(decryptBody(response.body, key, iv, limits));
  assert.deepEqual(value.putItems, { UserItemToken: 1, UserRandomSeed: 1 });
  assert.ok(value.dataTokens.ItemTokens && value.dataTokens.RandomSeeds);
  assert.equal(value.data.UserItemToken.length, 1); assert.ok(value.data.UserItemToken[0].signature);
  assert.equal(value.data.UserRandomSeed.length, 1); assert.ok(value.data.UserRandomSeed[0].signature);
  const tokenOnlySave = structuredClone(blockingSave);
  delete tokenOnlySave.deltas[0].putItems.UserRandomSeed;
  delete tokenOnlySave.dataTokens.UserRandomSeed;
  delete tokenOnlySave.checksums.before.UserRandomSeed; delete tokenOnlySave.checksums.after.UserRandomSeed;
  tokenOnlySave.dataTokens.UserItemToken = value.dataTokens.UserItemToken;
  response = await call(port, 'user_data/push', Buffer.from(JSON.stringify(tokenOnlySave)), true, true);
  assert.equal(response.status, 200);
  value = JSON.parse(decryptBody(response.body, key, iv, limits));
  assert.deepEqual(value.putItems, { UserItemToken: 1 });
  assert.equal(value.data.UserItemToken.length, 1); assert.ok(value.data.UserItemToken[0].signature);
  response = await call(port, 'user_data/confirm', Buffer.alloc(0), true, true);
  const currentTokens = JSON.parse(decryptBody(response.body, key, iv, limits)).dataTokens;
  const battleSave = structuredClone(blockingSave), partyRow = structuredClone(seed.tables.UserParty[0]);
  delete partyRow._id; partyRow.partyName = 'Battle save identity check';
  battleSave.deltas[0].trigger = 'BattleEnded'; battleSave.deltas[0].deleteItems = {};
  battleSave.deltas[0].putItems = { UserParty: [partyRow] };
  battleSave.dataTokens = { UserParty: currentTokens.UserParty };
  battleSave.checksums = { before: { UserParty: '0'.repeat(32) }, after: { UserParty: '0'.repeat(32) } };
  response = await call(port, 'user_data/push', Buffer.from(JSON.stringify(battleSave)), true, true);
  assert.equal(response.status, 200);
  value = JSON.parse(decryptBody(response.body, key, iv, limits));
  assert.deepEqual(value.putItems, { UserParty: 1 });
  response = await call(port, 'user_data/pull', Buffer.from(JSON.stringify(
    { tables: ['UserParty'], consistentRead: false, recovery: false })), true, true);
  const parties = decodeMsgpack(decryptBody(response.body, key, iv, limits)).data.UserParty;
  assert.equal(parties.length, seed.tables.UserParty.length);
  assert.equal(parties.find(row => row.id === partyRow.id).partyName, partyRow.partyName);
  const styleSave = structuredClone(blockingSave), styleTables = ['UserEnvironmentChangeGroup','UserInfo','UserPCStyle'];
  styleSave.deltas[0].trigger = 'UiClosed';
  styleSave.deltas[0].putItems = Object.fromEntries(styleTables.map(name => [name,
    structuredClone(Array.isArray(seed.tables[name]) ? seed.tables[name].slice(0, 1) : [seed.tables[name]])]));
  styleSave.dataTokens = Object.fromEntries(styleTables.map(name => [name, currentTokens[name]]));
  styleSave.checksums = { before: {}, after: {} };
  for (const name of styleTables) {
    styleSave.checksums.before[name] = '0'.repeat(32); styleSave.checksums.after[name] = '0'.repeat(32);
  }
  response = await call(port, 'user_data/push', Buffer.from(JSON.stringify(styleSave)), true, true);
  assert.equal(response.status, 200);
  value = JSON.parse(decryptBody(response.body, key, iv, limits));
  assert.deepEqual(value.putItems, { UserEnvironmentChangeGroup: 1, UserInfo: 1, UserPCStyle: 1 });
  response = await call(port, 'user_data/confirm', Buffer.alloc(0), true, true);
  const catTokens = JSON.parse(decryptBody(response.body, key, iv, limits)).dataTokens;
  const catSave = structuredClone(styleSave), catTables =
    ['UserCatDiary','UserEnvironmentChangeGroup','UserInfo','UserKeyItem','UserMigratoryEnemy','UserPC'];
  catSave.deltas[0].trigger = 'CatDiary';
  catSave.deltas[0].putItems = Object.fromEntries(catTables.map(name => [name, [structuredClone(
    name === 'UserKeyItem' ? { userId: seed.user_id, keyItemId: 1, amount: 1 } :
      (Array.isArray(seed.tables[name]) ? seed.tables[name][0] : seed.tables[name]))]]));
  catSave.deltas[0].deleteItems = { UserItemToken: [structuredClone(seed.tables.UserItemToken[0])] };
  const catMutationTables = [...catTables, 'UserItemToken'];
  catSave.dataTokens = Object.fromEntries(catMutationTables.map(name => [name, catTokens[name]]));
  catSave.checksums = { before: {}, after: {} };
  for (const name of catMutationTables) {
    catSave.checksums.before[name] = '0'.repeat(32); catSave.checksums.after[name] = '0'.repeat(32);
  }
  response = await call(port, 'user_data/push', Buffer.from(JSON.stringify(catSave)), true, true);
  assert.equal(response.status, 200);
  value = JSON.parse(decryptBody(response.body, key, iv, limits));
  assert.deepEqual(value.putItems, Object.fromEntries(catTables.map(name => [name, 1])));
  assert.deepEqual(value.deleteItems, { UserItemToken: 1 });
  response = await call(port, 'user_data/confirm', Buffer.alloc(0), true, true);
  const questTokens = JSON.parse(decryptBody(response.body, key, iv, limits)).dataTokens;
  const questSave = structuredClone(catSave);
  questSave.deltas[0].trigger = 'EventDone'; questSave.deltas[0].deleteItems = {};
  questSave.deltas[0].putItems = { UserQuest: [{ userId: seed.user_id, questId: 1, state: 1 }] };
  questSave.dataTokens = { UserQuest: questTokens.UserQuest };
  questSave.checksums = { before: { UserQuest: '0'.repeat(32) }, after: { UserQuest: '0'.repeat(32) } };
  response = await call(port, 'user_data/push', Buffer.from(JSON.stringify(questSave)), true, true);
  assert.equal(response.status, 200);
  value = JSON.parse(decryptBody(response.body, key, iv, limits));
  assert.deepEqual(value.putItems, { UserQuest: 1 });
  const saveReplay = { requestId, sequence, response: Buffer.from(response.body) };
  await new Promise(resolve => app.server.close(resolve));

  app = createMobileServer({ seed, codec, statePath, log: () => {} }); port = await listen(app);
  requestId = saveReplay.requestId - 1; sequence = saveReplay.sequence - 1;
  response = await call(port, 'user_data/push', Buffer.from(JSON.stringify(questSave)), true, true);
  assert.deepEqual(response.body, saveReplay.response);
  response = await call(port, 'user_data/pull', pullBody, true, true);
  value = decodeMsgpack(decryptBody(response.body, key, iv, limits));
  assert.equal(value.data.UserInfo.userId, seed.user_id);
  assert.equal(value.data.UserInfo.totalPlayingTime, eventSave.deltas[0].putItems.UserInfo[0].totalPlayingTime);
  assert.equal(value.data.UserKeyItem[0].keyItemId, 1);
  await new Promise(resolve => app.server.close(resolve));
  assert.equal(JSON.parse(fs.readFileSync(`${statePath}.bak`)).version, 1);

  const database = path.join(temp, 'profile.sqlite'), imported = JSON.parse(fs.readFileSync(statePath));
  app = createMobileServer({ seed, codec, database, initialState: imported, log: () => {} }); port = await listen(app);
  response = await call(port, 'user_data/confirm', Buffer.alloc(0), true, true);
  assert.equal(response.status, 200);
  const sqliteReplay = { requestId, sequence, response: Buffer.from(response.body) };
  await app.close();
  const { DatabaseSync } = require('node:sqlite'), db = new DatabaseSync(database, { readOnly: true });
  assert.equal(db.prepare('SELECT count(*) AS count FROM profile').get().count, 207);
  assert.ok(JSON.parse(db.prepare("SELECT data FROM profile WHERE name='UserPC'").get().data)
    .some(pc => Number.isSafeInteger(pc.destinyPoint) && pc.destinyPoint > 0));
  db.close();
  app = createMobileServer({ seed, codec, database, log: () => {} }); port = await listen(app);
  requestId = sqliteReplay.requestId - 1; sequence = sqliteReplay.sequence - 1;
  response = await call(port, 'user_data/confirm', Buffer.alloc(0), true, true);
  assert.deepEqual(response.body, sqliteReplay.response);
  const beforeFailure = app.state().last_sequence;
  const injector = new DatabaseSync(database);
  injector.exec("CREATE TRIGGER reject_state BEFORE UPDATE ON server_state BEGIN SELECT RAISE(ABORT,'test'); END;");
  injector.close();
  response = await call(port, 'user_data/confirm', Buffer.alloc(0), true, true);
  assert.equal(response.status, 503); assert.equal(app.state().last_sequence, beforeFailure);
  const cleanup = new DatabaseSync(database); cleanup.exec('DROP TRIGGER reject_state'); cleanup.close();
  requestId--; sequence--;
  response = await call(port, 'user_data/confirm', Buffer.alloc(0), true, true);
  assert.equal(response.status, 200);
  app.state().replies = Object.fromEntries(Array.from({ length: 1024 }, (_, index) => [`expired/${index}`, {}]));
  response = await call(port, 'user_data/confirm', Buffer.alloc(0), true, true);
  assert.equal(response.status, 200); assert.equal(Object.keys(app.state().replies).length, 1024);
  assert.equal(Object.hasOwn(app.state().replies, 'expired/0'), false);
  await app.close();
  const corruptDatabase = path.join(temp, 'corrupt.sqlite');
  fs.copyFileSync(database, corruptDatabase);
  const corrupt = fs.openSync(corruptDatabase, 'r+');
  fs.writeSync(corrupt, Buffer.alloc(16), 0, 16, 0); fs.closeSync(corrupt);
  assert.throws(() => createMobileServer({ seed, codec, database: corruptDatabase, log: () => {} }),
    /Corrupt SQLite profile/);
  fs.rmSync(temp, { recursive: true, force: true });
  console.log(`PASS: Android server recognizes ${ACTIONS.size} actions, implements ${SEMANTIC_ROUTES.size} non-stub routes, rejects untraced semantics, and preserves replay/SQLite state`);
})().catch(error => { console.error(error); process.exitCode = 1; });
