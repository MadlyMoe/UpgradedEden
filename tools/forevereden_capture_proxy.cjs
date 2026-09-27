'use strict';
// App-scoped capture proxy core. It forwards official traffic but persists only a sanitized private seed.
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const https = require('node:https');
const crypto = require('node:crypto');
const { encryptBody, decryptBody, decodeMsgpack } = require('./forevereden_transport.cjs');

const OFFICIAL_HOSTS = new Set(['api-us.another-eden.games', 'api-ap.another-eden.games', 'api-eu.another-eden.games',
  'bn-payment.wrightflyer.net', 'gl-payment.gree-apps.net']);
const CATALOG_FILES = new Map([
  ['/v1.0/payment/productlist', 'official-productlist.json'],
  ['/v1.0/payment/subscription/productlist', 'official-subscription-productlist.json'],
]);
const PREFIX = '/game_client/';
const UPSTREAM_PREFIX = '/game_client/';
const LIMITS = { plaintext: 16 * 1024 * 1024, ciphertext: 4 * 1024 * 1024 };
const PRIVATE_USER_ID = 193602641768;
const HOP_HEADERS = new Set(['connection','keep-alive','proxy-authenticate','proxy-authorization','te','trailer','transfer-encoding','upgrade']);
const hash = value => crypto.createHash('sha256').update(value).digest('hex');

function sanitizeProfile(login, profile, { randomBytes = crypto.randomBytes } = {}) {
  if (!login || typeof login !== 'object' || Array.isArray(login) || typeof login.aesIv !== 'string' || Buffer.byteLength(login.aesIv) !== 16)
    throw new Error('Unsupported login response');
  if (!profile || Object.keys(profile).sort().join(',') !== 'data,dataTokens,recovery' || profile.recovery !== false ||
      !profile.data || typeof profile.data !== 'object' || Array.isArray(profile.data) || Object.keys(profile.data).length !== 207 ||
      !profile.dataTokens || typeof profile.dataTokens !== 'object' || Array.isArray(profile.dataTokens))
    throw new Error('Expected one complete 207-table profile');
  const tokenEntries = Object.entries(profile.dataTokens);
  const aliases = tokenEntries.filter(([name]) => !Object.hasOwn(profile.data, name)).map(([name]) => name);
  if (tokenEntries.length < 207 || tokenEntries.length > 240 || aliases.length > 32 ||
      tokenEntries.some(([name, value]) => !/^[A-Za-z][A-Za-z0-9_]{0,79}$/.test(name) || !/^[0-9a-f]{32}$/i.test(value)))
    throw new Error('Unexpected profile tokens');
  const officialUser = profile.data.UserInfo?.userId;
  if (!Number.isSafeInteger(officialUser)) throw new Error('Missing official user identity');
  const privateUser = PRIVATE_USER_ID;
  const salt = randomBytes(16).toString('hex');
  let nodes = 0;
  function clean(value, keyPath = '') {
    if (++nodes > 2_000_000 || keyPath.split('/').length > 34) throw new RangeError('Profile structure bound');
    if (Array.isArray(value)) {
      if (value.length > 100000) throw new RangeError('Array bound');
      return value.map((item, index) => clean(item, `${keyPath}/${index}`));
    }
    if (value && typeof value === 'object') {
      const result = {};
      for (const [key, item] of Object.entries(value)) {
        if (key === 'userId') {
          if (item !== officialUser) throw new Error('Unexpected other account reference');
          result[key] = privateUser;
        } else if (key === '_id') {
          result[key] = hash(Buffer.from(`${salt}${keyPath}${String(item)}`)).slice(0, 24);
        } else if (key === 'voteToken') {
          if (item !== null) throw new Error('Nonempty external voting credential');
          result[key] = null;
        } else result[key] = clean(item, `${keyPath}/${key}`);
      }
      return result;
    }
    if (typeof value === 'number' && (!Number.isFinite(value) || !Number.isSafeInteger(value) && Number.isInteger(value)))
      throw new RangeError('Unsupported profile number');
    if (!['string','number','boolean'].includes(typeof value) && value !== null) throw new Error('Unsupported profile value');
    return value;
  }
  const privateLogin = { ...login };
  for (const key of ['aesIv','data','dataTokens']) delete privateLogin[key];
  privateLogin.apiUrl = 'http://127.0.0.1:28765/us/private';
  privateLogin.publicUrl = 'http://127.0.0.1:28765/unsupported';
  privateLogin.tdsdkUrl = 'http://127.0.0.1:28765/unsupported';
  for (const key of ['adColonyEnabled','reviewEnabled','rewardTapEnabled','serialCodeEnabled']) privateLogin[key] = false;
  privateLogin.remoteLogFlags = 0;
  privateLogin.remoteLogDb = 'forevereden-local';
  const seed = {
    schema_version: 1,
    user_id: privateUser,
    login: privateLogin,
    tables: clean(profile.data),
    token_aliases: { ItemTokens: 'UserItemToken', RandomSeeds: 'UserRandomSeed' },
    pull_content_type: 'application/x-msgpack',
    source_scope: 'authorized full official profile; sanitized on device; pending operations excluded',
  };
  const serialized = JSON.stringify(seed);
  if (serialized.includes(String(officialUser)) || serialized.includes(login.aesIv)) throw new Error('Official identity remains after sanitization');
  return seed;
}

function createCaptureState({ key, fallbackIV, outputDir, randomBytes = crypto.randomBytes, log = console.log }) {
  if (!Buffer.isBuffer(key) || key.length !== 32 || !Buffer.isBuffer(fallbackIV) || fallbackIV.length !== 16)
    throw new TypeError('Expected the frozen client body codec');
  let login = null, loginHash = null, sessionIV = null, exported = null;
  let forcedPull = false;
  let pullData = {}, pullTokens = {}, pullHashes = [];
  function publish() {
    if (!login || Object.keys(pullData).length !== 207 || exported) return exported;
    const pull = { data: pullData, dataTokens: pullTokens, recovery: false };
    const seed = sanitizeProfile(login, pull, { randomBytes });
    seed.source_login_sha256 = loginHash;
    seed.source_profile_sha256 = pullHashes.length === 1 ? pullHashes[0] : hash(Buffer.from(pullHashes.join('\n')));
    seed.source_profile_parts = pullHashes.length;
    const body = Buffer.from(`${JSON.stringify(seed)}\n`);
    fs.mkdirSync(outputDir, { recursive: true });
    const target = path.join(outputDir, `forevereden-profile-${hash(body).slice(0, 16)}.json`);
    const temporary = `${target}.tmp-${process.pid}`;
    fs.writeFileSync(temporary, body, { mode: 0o600, flag: 'wx' });
    fs.renameSync(temporary, target);
    exported = { path: target, sha256: hash(body), bytes: body.length, tables: Object.keys(seed.tables).length };
    log(JSON.stringify({ event: 'sanitized-profile-exported', ...exported }));
    sessionIV?.fill(0); sessionIV = null; login = null; pullData = {}; pullTokens = {}; pullHashes = [];
    return exported;
  }
  function observe(action, headers, wire) {
    if (exported) return exported;
    if (!['user/login','user_data/pull'].includes(action)) return null;
    if (!Buffer.isBuffer(wire) || wire.length > LIMITS.ciphertext) throw new RangeError('Response body bound');
    const iv = action === 'user/login' ? fallbackIV : sessionIV;
    if (!iv) throw new Error('Profile pull arrived before login IV');
    const plain = decryptBody(wire, key, iv, LIMITS);
    if (action === 'user/login') {
      const parsed = JSON.parse(plain);
      if (typeof parsed.aesIv !== 'string' || Buffer.byteLength(parsed.aesIv) !== 16) throw new Error('Invalid session IV');
      sessionIV?.fill(0); sessionIV = Buffer.from(parsed.aesIv);
      login = parsed; loginHash = hash(plain);
      pullData = {}; pullTokens = {}; pullHashes = [];
      if (Object.keys(parsed.data ?? {}).sort().join(',') !== 'UserStatus' || Object.keys(parsed.dataTokens ?? {}).sort().join(',') !== 'UserStatus')
        throw new Error('Unexpected login bootstrap tables');
      Object.assign(pullData, parsed.data); Object.assign(pullTokens, parsed.dataTokens);
    } else {
      const contentType = String(headers['content-type'] ?? headers['Content-Type'] ?? '').split(';', 1)[0].trim().toLowerCase();
      if (contentType !== 'application/x-msgpack') throw new Error('Unexpected profile content type');
      const parsed = decodeMsgpack(plain, LIMITS.plaintext);
      if (!parsed || Object.keys(parsed).sort().join(',') !== 'data,dataTokens,recovery' || parsed.recovery !== false ||
          !parsed.data || typeof parsed.data !== 'object' || Array.isArray(parsed.data) ||
          !parsed.dataTokens || typeof parsed.dataTokens !== 'object' || Array.isArray(parsed.dataTokens))
        throw new Error('Unexpected profile response');
      Object.assign(pullData, parsed.data); Object.assign(pullTokens, parsed.dataTokens);
      if (Object.keys(pullData).length > 207 || Object.keys(pullTokens).length > 240) throw new RangeError('Profile table bound');
      pullHashes.push(hash(plain));
    }
    plain.fill(0);
    return publish();
  }
  function forceFullPull(action, wire) {
    if (action !== 'user_data/confirm' || forcedPull || exported) return wire;
    if (!sessionIV) throw new Error('Profile confirmation arrived before login IV');
    const plain = decryptBody(wire, key, sessionIV, LIMITS);
    try {
      const parsed = JSON.parse(plain);
      const tokens = parsed?.dataTokens;
      if (parsed?.code !== 0 || !tokens || typeof tokens !== 'object' || Array.isArray(tokens))
        throw new Error('Unexpected profile confirmation');
      const profileTokens = Object.keys(tokens).filter(name => (name.startsWith('User') || ['ItemTokens','RandomSeeds'].includes(name)) &&
        typeof tokens[name] === 'string' && /^[0-9a-f]{32}$/i.test(tokens[name]));
      if (profileTokens.length < 207) throw new Error(`Only ${profileTokens.length} profile tokens were confirmed`);
      for (const name of profileTokens) tokens[name] = '0'.repeat(32);
      forcedPull = true;
      log(JSON.stringify({ event: 'full-profile-sync-requested', tables: profileTokens.length }));
      return encryptBody(Buffer.from(JSON.stringify(parsed)), key, sessionIV, LIMITS);
    } finally { plain.fill(0); }
  }
  return { observe, forceFullPull, result: () => exported };
}

function createCaptureProxy({ codec, outputDir, tls = null, upstreamRequest = https.request, log = console.log }) {
  if (!/^[0-9a-f]{32}$/.test(codec.official_lib_md5 ?? '')) throw new Error('Missing frozen official library identity');
  const state = createCaptureState({ key: Buffer.from(codec.key_hex, 'hex'), fallbackIV: Buffer.from(codec.fallback_iv_hex, 'hex'), outputDir, log });
  const options = { maxHeaderSize: 32768, headersTimeout: 5000, requestTimeout: 15000 };
  const handler = (req, res) => {
    const officialHost = String(req.socket.servername ?? '').toLowerCase();
    if (!OFFICIAL_HOSTS.has(officialHost)) {
      req.resume(); res.writeHead(421, { Connection: 'close', 'Content-Length': '0' }); return res.end();
    }
    const requestPath = req.url ?? '';
    const action = requestPath.startsWith(PREFIX) && !requestPath.includes('?') ? requestPath.slice(PREFIX.length) : '';
    const manifest = /^\/asset\/[0-9a-f]{40}\/pkm\/production-global-(?:us|ap|eu)\/version\.manifest\.(?:[1-9]|1[0-6])$/.test(requestPath);
    const catalogPath = requestPath.split('?', 1)[0];
    const catalog = CATALOG_FILES.has(catalogPath) && (requestPath === catalogPath || requestPath === `${catalogPath}?develop=1`);
    const length = req.headers['content-length'];
    const validApi = req.method === 'POST' && /^[a-z0-9_/-]{1,160}$/.test(action) && /^[0-9]{1,7}$/.test(length ?? '');
    const validManifest = req.method === 'GET' && manifest && (length === undefined || length === '0');
    const validCatalog = req.method === 'GET' && catalog && (length === undefined || length === '0');
    if ((!validApi && !validManifest && !validCatalog) || req.headers['transfer-encoding'] || Number(length ?? 0) > 1024 * 1024) {
      log(JSON.stringify({ event: 'capture-rejected', reason: 'RequestShape', method: req.method,
        path: String(req.url ?? '').split('?', 1)[0].slice(0, 200) }));
      req.resume(); res.writeHead(400, { Connection: 'close', 'Content-Length': '0' }); return res.end();
    }
    const chunks = []; let size = 0;
    req.on('data', chunk => { size += chunk.length; if (size > 1024 * 1024) req.destroy(); else chunks.push(chunk); });
    req.on('error', () => {});
    req.on('end', () => {
      if (size !== Number(length ?? 0)) { res.writeHead(400, { Connection: 'close', 'Content-Length': '0' }); return res.end(); }
      const requestBody = Buffer.concat(chunks, size);
      const headers = Object.fromEntries(Object.entries(req.headers).filter(([name]) => name !== 'host' && !HOP_HEADERS.has(name)));
      headers.host = officialHost; headers.connection = 'keep-alive';
      if (validApi && headers['x-kms-lib-hash'] !== codec.official_lib_md5) {
        log(JSON.stringify({ event: 'capture-rejected', action, reason: 'LibraryIdentity' }));
        res.writeHead(409, { Connection: 'close', 'Content-Length': '0' }); return res.end();
      }
      const upstream = upstreamRequest({ protocol: 'https:', hostname: officialHost, port: 443, method: req.method,
        path: validManifest || validCatalog ? requestPath : UPSTREAM_PREFIX + action, headers, servername: officialHost }, response => {
        const responseChunks = []; let responseSize = 0;
        const responseLimit = validManifest ? 64 * 1024 : LIMITS.ciphertext;
        response.on('data', chunk => { responseSize += chunk.length; if (responseSize > responseLimit) response.destroy(); else responseChunks.push(chunk); });
        response.on('end', () => {
          const originalBody = Buffer.concat(responseChunks, responseSize); let body = originalBody;
          try {
            if (response.statusCode === 200) {
              body = state.forceFullPull(action, originalBody);
              state.observe(action, response.headers, body);
              if (validCatalog) {
                const parsed = JSON.parse(body);
                if (parsed?.result !== 'OK' || !Array.isArray(parsed?.entry?.products) || parsed.entry.products.length > 128)
                  throw new Error('Unexpected catalog response');
                fs.mkdirSync(outputDir, { recursive: true });
                const target = path.join(outputDir, CATALOG_FILES.get(catalogPath)), temporary = `${target}.tmp-${process.pid}`;
                fs.writeFileSync(temporary, body, { mode: 0o600 }); fs.renameSync(temporary, target);
                log(JSON.stringify({ event: 'official-catalog-captured', catalog: catalogPath, products: parsed.entry.products.length }));
              }
            }
          } catch (error) {
            body = originalBody;
            log(JSON.stringify({ event: 'capture-rejected', action, reason: error.name, detail: String(error.message).slice(0, 160) }));
          }
          const outgoing = {};
          const rawHeaders = response.rawHeaders ?? Object.entries(response.headers).flat();
          for (let index = 0; index < rawHeaders.length; index += 2) {
            const name = rawHeaders[index], lower = name.toLowerCase();
            if (!HOP_HEADERS.has(lower) && lower !== 'content-length') outgoing[name] = rawHeaders[index + 1];
          }
          outgoing.Connection = response.headers.connection === 'close' ? 'close' : 'keep-alive';
          outgoing['Content-Length'] = String(body.length);
          res.writeHead(response.statusCode ?? 502, outgoing); res.end(body);
          log(JSON.stringify({ event: 'official-forward', action: validManifest ? 'version-manifest' : validCatalog ? catalogPath : action, status: response.statusCode,
            kms_code: response.headers['x-kms-server-response-code'] ?? null,
            request_id: response.headers['x-kms-request-id'] ?? null,
            sequence: response.headers['x-kms-request-sequence'] ?? null,
            request_bytes: size, response_bytes: body.length }));
        });
      });
      upstream.setTimeout(15000, () => upstream.destroy(new Error('Official request timeout')));
      upstream.on('error', error => { log(JSON.stringify({ event: 'official-forward-failed', action, reason: error.name })); if (!res.headersSent) res.writeHead(502, { Connection: 'close', 'Content-Length': '0' }); res.end(); });
      upstream.end(requestBody);
    });
  };
  const server = tls ? https.createServer({ ...options, ...tls }, handler) : http.createServer(options, handler);
  server.maxConnections = 4; server.maxHeadersCount = 64; server.keepAliveTimeout = 5000;
  if (tls) server.on('tlsClientError', error => log(JSON.stringify({ event: 'tls-client-error', reason: error.code ?? error.name })));
  server.on('clientError', (_error, socket) => socket.end('HTTP/1.1 400 Bad Request\r\nConnection: close\r\nContent-Length: 0\r\n\r\n'));
  return { server, state };
}

module.exports = { OFFICIAL_HOSTS, PREFIX, UPSTREAM_PREFIX, sanitizeProfile, createCaptureState, createCaptureProxy };

if (require.main === module) {
  const root = path.resolve(__dirname, '..');
  const codec = JSON.parse(fs.readFileSync(path.join(root, 'data/forevereden-evidence/private-login/body-codec-inputs.json')));
  const outputDir = path.join(root, 'data/forevereden-evidence/device-profile-exports');
  const app = createCaptureProxy({ codec, outputDir });
  app.server.listen(28765, '127.0.0.1', 4, () => console.log(JSON.stringify({ listening: 'http://127.0.0.1:28765', upstream: [...OFFICIAL_HOSTS], sanitized_exports: outputDir })));
}
