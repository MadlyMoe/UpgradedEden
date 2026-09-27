'use strict';
// One local startup server. Unsupported gameplay operations fail explicitly.
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');
const { DatabaseSync } = require('node:sqlite');
const { encryptBody, decryptBody, encodeMsgpack } = require('./forevereden_transport.cjs');
const { applySave } = require('./forevereden_save.cjs');
const ROOT = path.resolve(__dirname, '..');
const PORT = 28765;
const ACTIONS = ['matching_user/game_user_id','user/login','user/update_meta','user_data/confirm','user_data/pull','user_data/push','user/migration/status_reset'];
const LIMITS = { plaintext: 16 * 1024 * 1024, ciphertext: 4 * 1024 * 1024 };
const hash = (x, type = 'sha256') => crypto.createHash(type).update(x).digest('hex');
const canonical = x => Array.isArray(x) ? x.map(canonical) : x && typeof x === 'object'
  ? Object.fromEntries(Object.keys(x).sort().map(k => [k, canonical(x[k])])) : x;
const identityHash = x => hash(JSON.stringify(canonical(x)));
const fail = (status, message) => { throw Object.assign(new Error(message), { status }); };
function requireCondition(condition, message) { if (!condition) fail(400, message); }

function loadRuntime() {
  const manifest = JSON.parse(fs.readFileSync(path.join(ROOT, 'forevereden/local-runtime-identity.json')));
  const id = manifest.identity;
  if (manifest.runtime_id !== identityHash(id) || id.schema_version !== 1 || id.endpoint !== `http://127.0.0.1:${PORT}`)
    throw new Error('Unsupported local runtime identity');
  for (const [file, digest] of Object.entries(id.server)) {
    if (!['tools/forevereden_server.cjs','tools/forevereden_save.cjs','tools/forevereden_transport.cjs'].includes(file) || hash(fs.readFileSync(path.join(ROOT,file))) !== digest)
      throw new Error('Server source changed; republish the runtime identity');
  }
  const probe = JSON.parse(fs.readFileSync(path.join(ROOT, 'forevereden/private-probe-identity.json')));
  if (probe.runtime_id !== id.private_client_runtime_id || probe.runtime_id !== identityHash(probe.identity))
    throw new Error('Private client generation mismatch');
  function artifact(info) {
    const p = path.resolve(ROOT,info.path);
    if (path.dirname(p) !== path.join(ROOT,'data/forevereden-evidence/private-login')) throw new Error('Artifact path boundary');
    const b = fs.readFileSync(p);
    if (b.length > 8*1024*1024 || hash(b) !== info.sha256) throw new Error('Artifact identity mismatch');
    return JSON.parse(b);
  }
  const resources=new Map();
  for (const [route,info] of Object.entries(id.resource_routes ?? {})) {
    const p=path.resolve(ROOT,info.path);
    if (!new RegExp(`^/content/${id.content_generation}/(project|version)\\.manifest\\.([1-9]|1[0-6])$`).test(route) ||
        path.dirname(p)!==path.join(ROOT,'data/forevereden-evidence/private-resources') ||
        !/^(project|version)\.manifest\.([1-9]|1[0-6])\.json$/.test(path.basename(p)) ||
        !Number.isSafeInteger(info.bytes) || info.bytes<1 || info.bytes>32*1024*1024 || resources.size>=32)
      throw new Error('Invalid resource route identity');
    const body=fs.readFileSync(p);
    if(body.length!==info.bytes || hash(body)!==info.sha256) throw new Error('Resource manifest changed');
    resources.set(route,body);
  }
  return { manifest, seed: artifact(id.seed), codec: artifact(id.codec), resources };
}

function createServer({ runtime = loadRuntime(), database, enroll = false, log = console.log }) {
  const { manifest, seed, codec } = runtime;
  const id = manifest.identity;
  const routes = new Set(id.supported_routes);
  if (!Array.isArray(id.supported_routes) || routes.size !== id.supported_routes.length ||
      routes.size !== ACTIONS.length || ACTIONS.some(action => !routes.has(action)))
    throw new Error('Missing, duplicate or unsupported route ownership');
  if (id.publisher_migration !== 'disabled' || seed.login.accountMigrationStatus !== 0)
    throw new Error('Publisher migration state cannot be imported into a local-only account');
  const key = Buffer.from(codec.key_hex,'hex'), fallbackIV = Buffer.from(codec.fallback_iv_hex,'hex');
  if (key.length !== 32 || fallbackIV.length !== 16) throw new Error('Unsupported body codec inputs');
  const db = new DatabaseSync(database);
  db.exec('PRAGMA foreign_keys=ON; PRAGMA busy_timeout=3000; PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;');
  const schema = db.prepare('PRAGMA user_version').get().user_version;
  if (schema !== 0 && schema !== 1) throw new Error('Unsupported database schema; migration required');
  if (schema === 0) {
    db.exec(`BEGIN IMMEDIATE;
      CREATE TABLE runtime (id INTEGER PRIMARY KEY CHECK(id=1), runtime_id TEXT NOT NULL, seed_hash TEXT NOT NULL);
      CREATE TABLE account (id INTEGER PRIMARY KEY CHECK(id=1), user_id INTEGER NOT NULL, device_hash TEXT,
        capability TEXT NOT NULL, aes_iv TEXT NOT NULL, last_sequence TEXT NOT NULL, meta TEXT NOT NULL);
      CREATE TABLE profile (name TEXT PRIMARY KEY, data TEXT NOT NULL, token TEXT NOT NULL);
      CREATE TABLE replies (request_id TEXT NOT NULL, sequence TEXT NOT NULL, action TEXT NOT NULL,
        body_hash TEXT NOT NULL, token_hash TEXT NOT NULL, device_hash TEXT NOT NULL,
        headers TEXT NOT NULL, body BLOB NOT NULL, PRIMARY KEY(request_id,sequence));`);
    try {
      db.prepare('INSERT INTO runtime VALUES(1,?,?)').run(manifest.runtime_id,id.seed.sha256);
      db.prepare('INSERT INTO account VALUES(1,?,NULL,?,?,?,?)').run(seed.user_id,crypto.randomBytes(16).toString('hex'),crypto.randomBytes(8).toString('hex'),'-1','{}');
      const insert = db.prepare('INSERT INTO profile VALUES(?,?,?)');
      for (const [name,value] of Object.entries(seed.tables)) {
        const encoded = JSON.stringify(value);
        insert.run(name,encoded,hash(encoded,'md5'));
      }
      db.exec('PRAGMA user_version=1; COMMIT;');
    } catch (error) { db.exec('ROLLBACK'); throw error; }
  }
  const savedRuntime = db.prepare('SELECT * FROM runtime WHERE id=1').get();
  if (savedRuntime.runtime_id !== manifest.runtime_id || savedRuntime.seed_hash !== id.seed.sha256)
    throw new Error('Database belongs to another runtime; preserve it and migrate explicitly');
  const getAccount = db.prepare('SELECT * FROM account WHERE id=1');
  const getTable = db.prepare('SELECT * FROM profile WHERE name=?');
  const getReply = db.prepare('SELECT * FROM replies WHERE request_id=? AND sequence=?');
  const saveReply = db.prepare('INSERT INTO replies VALUES(?,?,?,?,?,?,?,?)');
  let shuttingDown = false;
  function dispatch(req, wire) {
    const match=req.url.match(/^\/(?:us|ap|eu)\/private\/game_client\//);
    requireCondition(req.method === 'POST' && match && !req.url.includes('?'), 'Unsupported request target');
    const action = req.url.slice(match[0].length);
    if (!routes.has(action)) fail(503,'Unsupported operation '+hash(action));
    requireCondition(req.headers.host === `127.0.0.1:${PORT}`, 'Host mismatch');
    requireCondition(req.headers['x-kms-client-version'] === '3.17.0' && req.headers['x-kms-client-version-code'] === '699', 'Client version mismatch');
    const requestId=req.headers['x-kms-request-id'], sequence=req.headers['x-kms-request-sequence'];
    requireCondition(/^[0-9]{1,10}$/.test(requestId ?? '') && BigInt(requestId) <= 2147483647n, 'Request ID bound');
    requireCondition(/^[0-9]{1,19}$/.test(sequence ?? '') && BigInt(sequence) <= 9223372036854775807n, 'Sequence bound');
    const token=req.headers['x-kms-one-time-token'] ?? '';
    requireCondition(typeof token === 'string' && token.length <= 128,'Capability bound');
    // The Android SDK leaves PLATFORM_USER_ID empty before its first login.
    // Device metadata is only a consistency hint; the private capability authenticates.
    const device=req.headers['x-kms-device'] ?? '';
    requireCondition(typeof device === 'string' && device.length <= 1024,'Device metadata bound');
    const deviceHash=hash(device), account=getAccount.get();
    const user=req.headers['x-kms-user'] ?? '';
    const authenticated = user === String(account.user_id) && token === account.capability && account.device_hash === deviceHash;
    // Explicit local pairing window: startup can retry before the SDK retains a token.
    // Never use device metadata alone for profile reads or a remotely exposed server.
    const newPair = enroll && token === '' && ['user/login','matching_user/game_user_id'].includes(action) &&
      (account.device_hash === null || account.device_hash === deviceHash);
    // The capability authorizes only these startup routes. It is not game integrity attestation.
    // Captured bootstrap calls all reuse 0/0, including across cold starts.
    // Only queued user_data calls carry a durable sequence/retry identity.
    const bootstrap = ['matching_user/game_user_id','user/login','user/update_meta'].includes(action);
    const old = bootstrap ? null : getReply.get(requestId,sequence);
    if (!authenticated && !newPair) {
      log(JSON.stringify({action,authentication:{user_matches:user===String(account.user_id),
        capability_matches:token===account.capability,device_matches:account.device_hash===deviceHash,
        user_present:user.length>0,capability_present:token.length>0}}));
      fail(401,'Local capability required');
    }
    const iv = ['matching_user/game_user_id','user/login'].includes(action) ? fallbackIV : Buffer.from(account.aes_iv);
    const mode=req.headers['x-kms-encryption'];
    requireCondition(mode === '0' || mode === '1', 'Unsupported encryption mode');
    const body=mode === '1' ? decryptBody(wire,key,iv,LIMITS) : wire;
    requireCondition(body.length <= LIMITS.plaintext,'Request body bound');
    const bodyHash=hash(body,'md5');
    requireCondition(req.headers['x-kms-request-body-hash'] === bodyHash,'Request body checksum mismatch');
    if (old) {
      requireCondition(old.action === action && old.body_hash === bodyHash && old.device_hash === deviceHash, 'Conflicting replay');
      return { action, headers:JSON.parse(old.headers), body:Buffer.from(old.body), replay:true };
    }
    if (!bootstrap) {
      requireCondition(BigInt(sequence) > BigInt(account.last_sequence),'Stale sequence');
      if (db.prepare('SELECT count(*) AS n FROM replies').get().n >= 1024) fail(503,'Startup capture reply budget exhausted');
    }
    let response, contentType='application/json', metadata=account.meta, save=null;
    function emptyBody() { requireCondition(body.length === 0,'Expected empty application body'); }
    function table(name) { const row=getTable.get(name); if (!row) fail(503,'Missing authoritative table'); return JSON.parse(row.data); }
    function tokens() {
      const result=Object.fromEntries(db.prepare('SELECT name,token FROM profile ORDER BY name').all().map(v=>[v.name,v.token]));
      for (const [alias,name] of Object.entries(seed.token_aliases)) result[alias]=result[name];
      return result;
    }
    if (action === 'user/login') {
      emptyBody();
      response={...seed.login, code:0, aesIv:account.aes_iv, data:{UserStatus:table('UserStatus')}, dataTokens:{UserStatus:getTable.get('UserStatus').token}};
    } else if (action === 'matching_user/game_user_id') {
      emptyBody(); response={code:0, game_user_id:account.user_id, aesIv:account.aes_iv};
    } else if (action === 'user/update_meta') {
      const value=JSON.parse(body);
      requireCondition(value && Object.keys(value).length === 1 && [0,1].includes(value.is32bit),'Unsupported client metadata');
      metadata=JSON.stringify(value); response={code:0};
    } else if (action === 'user_data/confirm') {
      emptyBody(); response={code:0,dataTokens:tokens(),migrators:[],operations:[]};
    } else if (action === 'user/migration/status_reset') {
      // EXTERNAL_COMPATIBILITY: this local account has no publisher transfer state.
      // Acknowledge that terminal state only; do not implement account transfer.
      emptyBody(); response={code:0};
    } else if (action === 'user_data/push') {
      const tables=Object.fromEntries(db.prepare('SELECT name,data FROM profile ORDER BY name').all().map(row=>[row.name,JSON.parse(row.data)]));
      save=applySave(JSON.parse(body),{userId:account.user_id,tables,tokenAliases:seed.token_aliases});
      response=save.response;
    } else if (action === 'user_data/pull') {
      const value=JSON.parse(body);
      requireCondition(value && Object.keys(value).sort().join(',') === 'consistentRead,recovery,tables' &&
        typeof value.consistentRead === 'boolean' && value.recovery === false && Array.isArray(value.tables) &&
        value.tables.length <= 207 && new Set(value.tables).size === value.tables.length, 'Unsupported profile pull');
      const data={}, allTokens=tokens(), dataTokens={};
      for (const name of value.tables) {
        requireCondition(typeof name === 'string' && /^[A-Za-z][A-Za-z0-9]{0,79}$/.test(name),'Table name bound');
        data[name]=table(name); dataTokens[name]=allTokens[name];
      }
      for (const [alias,name] of Object.entries(seed.token_aliases)) if (Object.hasOwn(data,name)) dataTokens[alias]=allTokens[alias];
      response={data,dataTokens,recovery:false};
      contentType=seed.pull_content_type;
    } else fail(503,'Unimplemented route');
    const plain=contentType === 'application/json' ? Buffer.from(JSON.stringify(response)) : encodeMsgpack(response);
    const encoded=encryptBody(plain,key,iv,LIMITS);
    const now=String(Math.floor(Date.now()/1000));
    const headers={'Content-Type':contentType,'Content-Length':String(encoded.length),'Cache-Control':'no-store','Connection':'close',
      'X-KMS-ENCRYPTION':'1','X-KMS-REQUEST-ID':requestId,'X-KMS-REQUEST-SEQUENCE':sequence,
      'X-KMS-REQUEST-BODY-HASH':bodyHash,'X-KMS-ONE-TIME-TOKEN':account.capability,'X-KMS-USER':String(account.user_id),
      'X-KMS-SERVER-RESPONSE-CODE':'0','X-KMS-SERVER-TIMESTAMP':now,'X-KMS-ACCEPT-TIMESTAMP':now,
      'X-KMS-SERVER-VERSION':'ForeverEden/1','X-KMS-WEBSHOP-LINK':'0'};
    // No runtime execution or socket writes while the transaction is open.
    db.exec('BEGIN IMMEDIATE');
    try {
      if (save) {
        const update=db.prepare('UPDATE profile SET data=?,token=? WHERE name=?');
        for (const name of save.mutationNames) {
          const data=JSON.stringify(save.nextTables[name]);
          if (update.run(data,hash(data,'md5'),name).changes !== 1) throw new Error('Missing save table');
        }
      }
      const changed=db.prepare('UPDATE account SET device_hash=?,last_sequence=?,meta=? WHERE id=1 AND last_sequence=?')
        .run(deviceHash,bootstrap ? account.last_sequence : sequence,metadata,account.last_sequence).changes;
      if (changed !== 1) throw new Error('Concurrent state change');
      if (!bootstrap) saveReply.run(requestId,sequence,action,bodyHash,hash(token),deviceHash,JSON.stringify(headers),encoded);
      db.exec('COMMIT');
    } catch (error) { db.exec('ROLLBACK'); throw error; }
    return {action,headers,body:encoded,replay:false};
  }
  const server=http.createServer({maxHeaderSize:32768,headersTimeout:5000,requestTimeout:10000},(req,res)=>{
    if (shuttingDown) { res.writeHead(503,{'Connection':'close'}); return res.end(); }
    const seen=new Set();
    for (let i=0;i<req.rawHeaders.length;i+=2) {
      const key=req.rawHeaders[i].toLowerCase();
      if (seen.has(key)) { res.writeHead(400,{'Connection':'close'}); res.end(); req.resume(); return; }
      seen.add(key);
    }
    // Immutable asset metadata is public content, never an account/session route.
    const resource=runtime.resources?.get(req.url);
    if(resource && req.method==='GET' && req.headers.host===`127.0.0.1:${PORT}` &&
        !req.headers['transfer-encoding'] && (!req.headers['content-length'] || req.headers['content-length']==='0')) {
      log(JSON.stringify({utc:new Date().toISOString(),resource:req.url,status:200,response_bytes:resource.length}));
      res.writeHead(200,{'Content-Type':'application/json','Content-Length':String(resource.length),'Connection':'close'});
      res.end(resource);req.resume();return;
    }
    const length=req.headers['content-length'];
    if (req.headers['transfer-encoding'] || !/^[0-9]{1,7}$/.test(length ?? '') || Number(length)>LIMITS.ciphertext) {
      res.writeHead(413,{'Connection':'close'}); res.end(); req.resume(); return;
    }
    const parts=[]; let size=0;
    req.setTimeout(5000,()=>req.destroy());
    req.on('data',b=>{size+=b.length; if(size>LIMITS.ciphertext) req.destroy(); else parts.push(b);});
    req.on('error',()=>{});
    req.on('end',()=>{
      try {
        requireCondition(size===Number(length),'Request length mismatch');
        const result=dispatch(req,Buffer.concat(parts,size));
        log(JSON.stringify({utc:new Date().toISOString(),runtime_id:manifest.runtime_id,action:result.action,status:200,
          request_bytes:size,response_bytes:result.body.length,replay:result.replay}));
        res.writeHead(200,result.headers); res.end(result.body);
      } catch (error) {
        const status=error.status ?? (error instanceof SyntaxError || error instanceof RangeError ? 400 : 503);
        log(JSON.stringify({utc:new Date().toISOString(),status,reason:error.status ? error.message : error.name}));
        res.writeHead(status,{'Content-Length':'0','Connection':'close','Cache-Control':'no-store'}); res.end();
      }
    });
  });
  server.maxConnections=8; server.maxHeadersCount=64; server.keepAliveTimeout=1000;
  server.on('clientError',(_error,socket)=>socket.end('HTTP/1.1 400 Bad Request\r\nConnection: close\r\nContent-Length: 0\r\n\r\n'));
  return {server,db,close:()=>new Promise(resolve=>{shuttingDown=true;server.close(()=>{db.close();resolve();});server.closeIdleConnections();})};
}

module.exports={createServer,loadRuntime,identityHash};
if (require.main===module) {
  const args=process.argv.slice(2);
  if (args.some(v=>v!=='--enroll')) throw new Error('Only --enroll is supported');
  const runtime=loadRuntime();
  const directory=path.join(ROOT,'data/forevereden-evidence/private-login');
  const app=createServer({runtime,database:path.join(directory,'profile.sqlite'),enroll:args.includes('--enroll')});
  app.server.listen(PORT,'127.0.0.1',8,()=>console.log(JSON.stringify({listening:`http://127.0.0.1:${PORT}`,runtime_id:runtime.manifest.runtime_id,enrollment:args.includes('--enroll')})));
  for (const signal of ['SIGINT','SIGTERM']) process.on(signal,()=>{app.close().then(()=>process.exit());});
}
