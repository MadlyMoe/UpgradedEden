'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs'), os=require('node:os'), path=require('node:path'), http=require('node:http'), crypto=require('node:crypto');
const {spawnSync}=require('node:child_process');
const {createServer,loadRuntime}=require('./forevereden_server.cjs');
const {encryptBody,decryptBody,encodeMsgpack}=require('./forevereden_transport.cjs');
const ROOT=path.resolve(__dirname,'..');
const runtime=loadRuntime(), key=Buffer.from(runtime.codec.key_hex,'hex'), fallback=Buffer.from(runtime.codec.fallback_iv_hex,'hex');
const limits={plaintext:8*1024*1024,ciphertext:4*1024*1024};
const native=JSON.parse(fs.readFileSync(path.join(ROOT,'data/forevereden-evidence/original-transport-codec-check.json')));
for(const f of native.fixtures){
  const k=Buffer.from([...Array(32).keys()]),iv=Buffer.from([...Array(16).keys()]);
  assert.deepEqual(encryptBody(Buffer.from(f.plaintext_hex,'hex'),k,iv,limits),Buffer.from(f.ciphertext_hex,'hex'));
}
const captured=JSON.parse(fs.readFileSync(path.join(ROOT,'data/forevereden-evidence/private-login/wire-codec-fixtures.json')));
for(const f of captured) assert.deepEqual(decryptBody(Buffer.from(f.ciphertext_hex,'hex'),key,Buffer.from(f.iv_hex,'hex'),limits),Buffer.from(f.plaintext_hex,'hex'));
assert.throws(()=>decryptBody(Buffer.alloc(17),key,fallback,limits));
assert.throws(()=>encodeMsgpack({x:NaN}));
assert.throws(()=>encodeMsgpack({x:2**53}));
assert.throws(()=>encodeMsgpack('too large',2));
function checkMessagePack(value,encoded){
  const p=spawnSync('python',['-c','import json,sys;from pip._vendor import msgpack;x=json.load(sys.stdin);assert msgpack.unpackb(bytes.fromhex(x["hex"]),raw=False)==x["value"];print("PASS")'],
    {input:JSON.stringify({value,hex:encoded.toString('hex')}),encoding:'utf8',env:{...process.env,PYTHONUTF8:'1'},maxBuffer:8*1024*1024});
  assert.equal(p.status,0,p.stderr);assert.equal(p.stdout.trim(),'PASS');
}
checkMessagePack(runtime.seed.tables,encodeMsgpack(runtime.seed.tables));
checkMessagePack([-33,-129,-32769,-2147483649,128,256,65536,4294967296,Number.MAX_SAFE_INTEGER,1.25,null,true,'é'.repeat(130)],
 encodeMsgpack([-33,-129,-32769,-2147483649,128,256,65536,4294967296,Number.MAX_SAFE_INTEGER,1.25,null,true,'é'.repeat(130)]));
console.log('PASS: 17 original native codec fixtures, five captured encrypted responses, 207-table MessagePack semantics and bounds');
for (const actions of [runtime.manifest.identity.supported_routes.slice(1),
 [...runtime.manifest.identity.supported_routes,'user/login'],
 [...runtime.manifest.identity.supported_routes.slice(1),'invented/route']]) {
 const changed={...runtime,manifest:{...runtime.manifest,identity:{...runtime.manifest.identity,supported_routes:actions}}};
 assert.throws(()=>createServer({runtime:changed,database:':memory:'}),/route ownership/);
}
assert.throws(()=>createServer({runtime:{...runtime,seed:{...runtime.seed,login:{...runtime.seed.login,accountMigrationStatus:1}}},database:':memory:'}),/migration state/);

(async()=>{
 const temp=fs.mkdtempSync(path.join(os.tmpdir(),'forevereden-login-check-'));
 const database=path.join(temp,'test.sqlite');let app;
 const logs=[];
 let capability='', user='', iv=fallback;
 async function open(enroll){
  app=createServer({runtime,database,enroll,log:x=>logs.push(JSON.parse(x))});
  await new Promise(r=>app.server.listen(0,'127.0.0.1',r));
 }
 function request(action,id,sequence,value=null,overrides={}){
  const body=value===null?Buffer.alloc(0):Buffer.from(JSON.stringify(value));
  const wire=encryptBody(body,key,['matching_user/game_user_id','user/login'].includes(action)?fallback:iv,limits);
  return new Promise((resolve,reject)=>{
   const req=http.request({hostname:'127.0.0.1',port:app.server.address().port,path:'/us/private/game_client/'+action,method:'POST',
    headers:{Host:'127.0.0.1:28765','Content-Length':String(wire.length),'Content-Type':'application/json',
     'X-KMS-CLIENT-VERSION':'3.17.0','X-KMS-CLIENT-VERSION-CODE':'699','X-KMS-REQUEST-ID':String(id),
     'X-KMS-REQUEST-SEQUENCE':String(sequence),'X-KMS-PLATFORM_USER_ID':'','X-KMS-DEVICE':'local-test-device',
     'X-KMS-USER':user,'X-KMS-ONE-TIME-TOKEN':capability,'X-KMS-ENCRYPTION':'1',
     'X-KMS-REQUEST-BODY-HASH':crypto.createHash('md5').update(body).digest('hex'),...overrides}},res=>{
      const parts=[];res.on('data',x=>parts.push(x));res.on('end',()=>resolve({status:res.statusCode,headers:res.headers,body:Buffer.concat(parts)}));
   });req.on('error',reject);req.end(wire);
  });
 }
 function json(r,decodeIV=iv){assert.equal(r.status,200);return JSON.parse(decryptBody(r.body,key,decodeIV,limits));}
 try{
  await open(true);
  for(const [route,body] of runtime.resources ?? []) {
    const actual=await new Promise((resolve,reject)=>{
      http.get({hostname:'127.0.0.1',port:app.server.address().port,path:route,headers:{Host:'127.0.0.1:28765'}},res=>{
        const chunks=[];res.on('data',x=>chunks.push(x));res.on('end',()=>resolve({status:res.statusCode,body:Buffer.concat(chunks)}));
      }).on('error',reject);
    });
    assert.equal(actual.status,200);assert.deepEqual(actual.body,body);
    const data=JSON.parse(actual.body);
    assert.equal(data.version,runtime.manifest.identity.content_generation);
    assert(data.remoteVersionUrl.startsWith('http://127.0.0.1:28765/content/'));
    assert(data.remoteManifestUrl.startsWith('http://127.0.0.1:28765/content/'));
  }
  assert.equal((await request('user_data/confirm',0,0)).status,401);
  const first=await request('user/login',0,0);const login=json(first);
  assert.equal(login.apiUrl,'http://127.0.0.1:28765/us/private');
  assert.equal(login.data.UserStatus.userId,runtime.seed.user_id);
  capability=first.headers['x-kms-one-time-token'];user=first.headers['x-kms-user'];iv=Buffer.from(login.aesIv);
  assert.equal(json(await request('matching_user/game_user_id',0,0),fallback).game_user_id,runtime.seed.user_id);
  assert.equal((await request('user/update_meta',0,0,{is32bit:0},{'X-KMS-ONE-TIME-TOKEN':'wrong'})).status,401);
  const meta=await request('user/update_meta',0,0,{is32bit:0});assert.deepEqual(json(meta),{code:0});
  const again=await request('user/update_meta',0,0,{is32bit:0});assert.deepEqual(again.body,meta.body);
  assert.equal(app.db.prepare('SELECT count(*) AS n FROM replies').get().n,0);
  assert.equal(app.db.prepare('SELECT last_sequence FROM account').get().last_sequence,'-1');
  assert.equal((await request('user/login',0,0,null,{'X-KMS-USER':'0','X-KMS-ONE-TIME-TOKEN':''})).status,200);
  assert.equal((await request('user_data/confirm',0,11,null,{'X-KMS-USER':'0','X-KMS-ONE-TIME-TOKEN':''})).status,401);
  assert.equal(json(await request('user_data/confirm',0,11)).code,0);
  const pullValue={tables:['UserInfo','UserCurrency'],consistentRead:false,recovery:false};
  const pull=await request('user_data/pull',1,12,pullValue);
  assert.deepEqual((await request('user_data/pull',1,12,pullValue)).body,pull.body);
  assert.equal((await request('user_data/pull',1,12,{...pullValue,consistentRead:true})).status,400);
  assert.equal((await request('user_data/confirm',2,10)).status,400);
  assert.equal(pull.status,200);assert.equal(pull.headers['content-type'],runtime.seed.pull_content_type);
  const plain=decryptBody(pull.body,key,iv,limits);
  const decode=spawnSync('python',['-c','import sys,json;from pip._vendor import msgpack;x=msgpack.unpackb(sys.stdin.buffer.read(),raw=False);print(json.dumps({"tables":list(x["data"]),"recovery":x["recovery"]}))'],{input:plain,encoding:null});
  assert.equal(decode.status,0);assert.deepEqual(JSON.parse(decode.stdout),{tables:['UserInfo','UserCurrency'],recovery:false});
  app.db.exec("CREATE TRIGGER inject_failure BEFORE UPDATE ON account BEGIN SELECT RAISE(ABORT,'injected'); END;");
  assert.equal((await request('user/update_meta',0,0,{is32bit:1})).status,503);
  assert.equal(app.db.prepare('SELECT meta,last_sequence FROM account').get().meta,'{"is32bit":0}');
  assert.equal(app.db.prepare('SELECT count(*) AS n FROM replies').get().n,2);
  app.db.exec('DROP TRIGGER inject_failure');
  assert.deepEqual(json(await request('user/update_meta',0,0,{is32bit:1})),{code:0});
  const saveValue=JSON.parse(fs.readFileSync(path.join(ROOT,'data/forevereden-evidence/private-login/first-gameplay-push-request-2d385cd2462bf45f.json')));
  const setIdentity=value=>{ if(Array.isArray(value)) return value.forEach(setIdentity); if(!value||typeof value!=='object') return;
    for(const [key,item] of Object.entries(value)) if(key==='userId') value[key]=runtime.seed.user_id; else setIdentity(item); };
  setIdentity(saveValue); saveValue.deltas[0].trigger='ExplorerScheduled';
  saveValue.dataTokens=Object.fromEntries(Object.keys(saveValue.dataTokens).map(name=>[name,app.db.prepare('SELECT token FROM profile WHERE name=?').get(name).token]));
  const saveResponse=await request('user_data/push',5,13,saveValue);
  assert.equal(saveResponse.status,200); assert.deepEqual(json(saveResponse).triggers,['ExplorerScheduled']);
  await app.close();app=null;await open(false);
  assert.equal((await request('user/login',0,0,null,{'X-KMS-USER':'0','X-KMS-ONE-TIME-TOKEN':''})).status,401);
  assert.equal(app.db.prepare('SELECT meta FROM account').get().meta,'{"is32bit":1}');
  assert.deepEqual((await request('user_data/pull',1,12,pullValue)).body,pull.body);
  assert.equal(json(await request('user/login',0,0),fallback).data.UserStatus.userId,runtime.seed.user_id);
  assert.equal(json(await request('matching_user/game_user_id',0,0),fallback).game_user_id,runtime.seed.user_id);
  assert.deepEqual(json(await request('user/update_meta',0,0,{is32bit:0})),{code:0});
  assert.equal(app.db.prepare('SELECT last_sequence FROM account').get().last_sequence,'13');
  assert.equal((await request('user_data/pull',2,14,{tables:['InventedTable'],consistentRead:false,recovery:false})).status,503);
  assert.equal((await request('user_data/confirm',2,14,null,{'X-KMS-REQUEST-BODY-HASH':'0'.repeat(32)})).status,400);
  assert.equal((await request('user/migration/status_reset',0,14,null,{'X-KMS-ONE-TIME-TOKEN':''})).status,401);
  assert.equal((await request('user/migration/status_reset',0,14,{})).status,400);
  const profileBefore=app.db.prepare('SELECT name,data,token FROM profile ORDER BY name').all();
  app.db.exec("CREATE TRIGGER migration_failure BEFORE INSERT ON replies BEGIN SELECT RAISE(ABORT,'injected'); END;");
  assert.equal((await request('user/migration/status_reset',0,14)).status,503);
  assert.equal(app.db.prepare('SELECT last_sequence FROM account').get().last_sequence,'13');
  app.db.exec('DROP TRIGGER migration_failure');
  const terminal=await request('user/migration/status_reset',0,14);
  assert.deepEqual(json(terminal),{code:0});
  assert.deepEqual((await request('user/migration/status_reset',0,14)).body,terminal.body);
  await app.close();app=null;await open(false);
  assert.deepEqual((await request('user/migration/status_reset',0,14)).body,terminal.body);
  assert.deepEqual(app.db.prepare('SELECT name,data,token FROM profile ORDER BY name').all(),profileBefore);
  assert(logs.some(x=>x.replay===true));
  assert(!JSON.stringify(logs).includes(capability));
  console.log('PASS: real HTTP enrollment, encrypted login/pull/save, persistence, exact replay, rollback and restart');
 }finally{
  if(app) await app.close();
  // Only the three known files in this newly created test directory are removed.
  assert.equal(path.dirname(temp),path.resolve(os.tmpdir()));
  assert(path.basename(temp).startsWith('forevereden-login-check-'));
  for(const name of ['test.sqlite','test.sqlite-wal','test.sqlite-shm']) {const p=path.join(temp,name);if(fs.existsSync(p))fs.unlinkSync(p);}
  fs.rmdirSync(temp);
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
