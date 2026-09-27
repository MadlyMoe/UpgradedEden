'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const https = require('node:https');
const { createCipheriv } = require('node:crypto');
const { PassThrough } = require('node:stream');
const { deflateSync } = require('node:zlib');
const { encryptBody, decryptBody, encodeMsgpack, decodeMsgpack } = require('./forevereden_transport.cjs');
const { PREFIX, UPSTREAM_PREFIX, createCaptureState, createCaptureProxy } = require('./forevereden_capture_proxy.cjs');

assert.equal(PREFIX + 'user/login', '/game_client/user/login');
assert.equal(UPSTREAM_PREFIX + 'user/login', '/game_client/user/login');

const root = path.resolve(__dirname, '..');
const capture = path.join(root, 'data/forevereden-evidence/official-login/20260926T045127Z');
const codec = JSON.parse(fs.readFileSync(path.join(root, 'data/forevereden-evidence/private-login/body-codec-inputs.json')));
const key = Buffer.from(codec.key_hex, 'hex'), fallbackIV = Buffer.from(codec.fallback_iv_hex, 'hex');
const limits = { plaintext: 16 * 1024 * 1024, ciphertext: 4 * 1024 * 1024 };
const alignedPlain = Buffer.from('0827466584a3c2e1', 'hex'), alignedCompressed = deflateSync(alignedPlain);
assert.equal(alignedCompressed.length, 16);
const alignedCipher = createCipheriv('aes-256-cbc', key, fallbackIV); alignedCipher.setAutoPadding(false);
const fullBlockWire = Buffer.concat([alignedCipher.update(Buffer.concat([alignedCompressed, Buffer.alloc(16, 16)])), alignedCipher.final()]);
assert.deepEqual(decryptBody(fullBlockWire, key, fallbackIV, limits), alignedPlain);
const loginWire = fs.readFileSync(path.join(capture, '007-response-wire-body.bin'));
const loginPlain = decryptBody(loginWire, key, fallbackIV, limits);
const officialLogin = JSON.parse(loginPlain);
const confirmWire = fs.readFileSync(path.join(capture, '015-response-wire-body.bin'));
const pullWire = fs.readFileSync(path.join(capture, '020-response-wire-body.bin'));
const pullPlain = decryptBody(pullWire, key, Buffer.from(officialLogin.aesIv), limits);
const officialProfile = decodeMsgpack(pullPlain);
assert.equal(Object.keys(officialProfile.data).length, 207);
assert.deepEqual(decodeMsgpack(encodeMsgpack(officialProfile)), officialProfile);
const partialProfile = structuredClone(officialProfile);
delete partialProfile.data.UserStatus;
delete partialProfile.dataTokens.UserStatus;
const partialWire = encryptBody(encodeMsgpack(partialProfile), key, Buffer.from(officialLogin.aesIv), limits);
assert.equal(Object.keys(partialProfile.data).length, 206);

const outputDir = fs.mkdtempSync(path.join(os.tmpdir(), 'forevereden-capture-'));
let counter = 0;
const randomBytes = size => Buffer.alloc(size, ++counter);
const state = createCaptureState({ key, fallbackIV, outputDir, randomBytes, log: () => {} });
assert.equal(state.observe('user/login', { 'content-type': 'application/json' }, loginWire), null);
const result = state.observe('user_data/pull', { 'content-type': 'application/x-msgpack' }, partialWire);
assert.equal(result.tables, 207);
const body = fs.readFileSync(result.path, 'utf8');
const seed = JSON.parse(body);
assert.equal(seed.schema_version, 1);
assert.equal(seed.user_id, 193602641768);
assert.equal(seed.tables.UserInfo.userId, seed.user_id);
assert.equal(body.includes(String(officialProfile.data.UserInfo.userId)), false);
assert.equal(body.includes(officialLogin.aesIv), false);
assert.equal(body.includes('x-kms-one-time-token'), false);
assert.equal(seed.source_profile_parts, 1);
assert.equal(state.observe('user_data/pull', { 'content-type': 'application/x-msgpack' }, partialWire), result);
fs.rmSync(outputDir, { recursive: true, force: true });

const rewriteState = createCaptureState({ key, fallbackIV, outputDir, randomBytes, log: () => {} });
rewriteState.observe('user/login', { 'content-type': 'application/json' }, loginWire);
const forcedConfirm = rewriteState.forceFullPull('user_data/confirm', confirmWire);
const forcedTokens = JSON.parse(decryptBody(forcedConfirm, key, Buffer.from(officialLogin.aesIv), limits)).dataTokens;
const forcedProfileTokens = Object.entries(forcedTokens).filter(([name]) => name.startsWith('User') || ['ItemTokens','RandomSeeds'].includes(name));
assert.equal(forcedProfileTokens.length >= 207, true);
assert.equal(forcedProfileTokens.every(([, value]) => value === '0'.repeat(32)), true);
assert.notEqual(forcedTokens.GamelibPaymentUsers, '0'.repeat(32));
assert.deepEqual(rewriteState.forceFullPull('user_data/confirm', confirmWire), confirmWire);

function call(port, action, agent, method = 'POST', servername = 'api-ap.another-eden.games') {
  return new Promise((resolve, reject) => {
    const req = https.request({ hostname: '127.0.0.1', port, path: method === 'GET' ? action : PREFIX + action, method,
      servername, rejectUnauthorized: false, agent,
      headers: method === 'GET' ? {} : { 'Content-Length': '0', 'X-KMS-LIB-HASH': codec.official_lib_md5 } }, response => {
      const chunks = []; response.on('data', chunk => chunks.push(chunk));
      response.on('end', () => resolve({ body: Buffer.concat(chunks), headers: response.headers, rawHeaders: response.rawHeaders }));
    });
    req.on('error', reject); req.end();
  });
}
(async () => {
  const tlsOutput = fs.mkdtempSync(path.join(os.tmpdir(), 'forevereden-tls-capture-'));
  const manifestBody = Buffer.from('{"version":"test"}');
  const catalogBody = Buffer.from('{"result":"OK","entry":{"products":[{"product_id":"games.wfs.anothereden.gem.set.0101","name":"Chronos Stones","price":"$0.00","description":"Test","thumbnail_url":""}]}}');
  const upstreamRequest = (options, callback) => {
    assert.equal(['api-ap.another-eden.games', 'bn-payment.wrightflyer.net'].includes(options.hostname), true);
    const request = new PassThrough(); request.setTimeout = () => request;
    request.on('finish', () => {
      const catalog = options.hostname === 'bn-payment.wrightflyer.net';
      const manifest = options.method === 'GET' && !catalog, login = options.path.endsWith('/user/login');
      const response = new PassThrough(); response.statusCode = 200;
      response.headers = { 'content-type': manifest || login || catalog ? 'application/json' : 'application/x-msgpack' };
      response.rawHeaders = ['Content-Type', response.headers['content-type'], 'X-KMS-SERVER-RESPONSE-CODE', '0', 'Connection', 'keep-alive'];
      callback(response); response.end(catalog ? catalogBody : manifest ? manifestBody : login ? loginWire : partialWire);
    });
    return request;
  };
  const app = createCaptureProxy({ codec, outputDir: tlsOutput, upstreamRequest, log: () => {}, tls: {
    key: fs.readFileSync(path.join(root, 'android/forevereden-launcher/app/src/main/assets/runtime/capture-key.pem')),
    cert: fs.readFileSync(path.join(root, 'android/forevereden-launcher/app/src/main/assets/runtime/capture-cert.pem')),
  } });
  await new Promise(resolve => app.server.listen(0, '127.0.0.1', resolve));
  const port = app.server.address().port;
  const agent = new https.Agent({ keepAlive: true, maxSockets: 1 });
  const loginResponse = await call(port, 'user/login', agent);
  assert.deepEqual(loginResponse.body, loginWire);
  assert.equal(loginResponse.headers.connection, 'keep-alive');
  assert.equal(loginResponse.rawHeaders.includes('X-KMS-SERVER-RESPONSE-CODE'), true);
  assert.deepEqual((await call(port, '/asset/0123456789abcdef0123456789abcdef01234567/pkm/production-global-us/version.manifest.1', agent, 'GET')).body, manifestBody);
  assert.deepEqual((await call(port, '/v1.0/payment/productlist?develop=1', agent, 'GET', 'bn-payment.wrightflyer.net')).body, catalogBody);
  assert.deepEqual((await call(port, 'user_data/pull', agent)).body, partialWire);
  agent.destroy();
  assert.deepEqual(fs.readFileSync(path.join(tlsOutput, 'official-productlist.json')), catalogBody);
  assert.equal(fs.readdirSync(tlsOutput).filter(name => name.endsWith('.json')).length, 2);
  await new Promise(resolve => app.server.close(resolve));
  fs.rmSync(tlsOutput, { recursive: true, force: true });
  console.log('PASS: non-root TLS bridge captures exact billing catalogs and exports a token-free 207-table profile');
})().catch(error => { console.error(error); process.exitCode = 1; });
