"""Prepare one private starter seed from an explicitly authorized local capture.

No requests to the official service. Raw identifiers/tokens are never printed.
This is an import fixture, not a recurring overlay on a saved profile.
"""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import sys

import forevereden_client as client
import forevereden_probe as probe

OUT = client.ROOT / 'data/forevereden-evidence/private-login'
ACTIVE = client.ROOT / 'forevereden/local-runtime-identity.json'


def prepare(capture, migrate_database=False):
    private, _ = probe.verify_probe()
    from pip._vendor import msgpack  # Existing bundled codec; preparation only.
    index = json.loads((capture / 'index.json').read_text())
    def read(kind, action):
        row, = [v for v in index if v.get('kind') == kind and v.get('action') == action]
        path = capture / row['file']
        if path.resolve().parent != capture.resolve() or client.digest(path) != row['sha256']:
            raise ValueError('Capture member identity mismatch')
        data = path.read_bytes()
        if len(data) != row['bytes'] or len(data) > 16*1024**2:
            raise ValueError('Capture member length mismatch')
        return data
    provenance = json.loads((capture / 'provenance.json').read_text())
    if provenance['runtime_id'] != private['identity']['parent_runtime_id']:
        raise ValueError('Capture does not belong to the frozen original client')
    login = json.loads(read('response-plaintext', 'user/login'))
    original_iv = login.pop('aesIv')
    profile = msgpack.unpackb(read('response-plaintext', 'user_data/pull'), raw=False,
        strict_map_key=True, max_str_len=4*1024**2, max_bin_len=4*1024**2,
        max_array_len=100000, max_map_len=100000)
    if set(profile) != {'data','dataTokens','recovery'} or profile['recovery'] is not False:
        raise ValueError('Unsupported profile envelope')
    if len(profile['data']) != 207 or set(profile['dataTokens']) - set(profile['data']) != {'ItemTokens','RandomSeeds'}:
        raise ValueError('Unexpected starter table set')
    official_user = profile['data']['UserInfo']['userId']
    user = secrets.randbelow(800000000000) + 100000000000
    salt = secrets.token_hex(16)
    def sanitize(value, path=''):
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if key == 'userId':
                    if item != official_user:
                        raise ValueError('Unexpected other account reference')
                    result[key] = user
                elif key == '_id':
                    result[key] = hashlib.sha256((salt+path+str(item)).encode()).hexdigest()[:24]
                elif key == 'voteToken':
                    if item is not None:
                        raise ValueError('Review nonempty external voting credential')
                    result[key] = None
                else:
                    result[key] = sanitize(item, path+'/'+key)
            return result
        if isinstance(value,list):
            return [sanitize(v,path+'/'+str(i)) for i,v in enumerate(value)]
        if isinstance(value,int) and abs(value) > 2**53-1:
            raise ValueError('Starter integer exceeds the supported JavaScript range')
        if not isinstance(value,(str,int,float,bool,type(None))):
            raise ValueError('Unsupported starter value type')
        return value
    data = sanitize(profile['data'])
    login.pop('data'); login.pop('dataTokens')
    login['apiUrl'] = probe.ENDPOINT + '/us/private'
    login['publicUrl'] = probe.ENDPOINT + '/unsupported'
    login['tdsdkUrl'] = probe.ENDPOINT + '/unsupported'
    for flag in ('adColonyEnabled','reviewEnabled','rewardTapEnabled','serialCodeEnabled'):
        login[flag] = False
    login['remoteLogFlags'] = 0
    login['remoteLogDb'] = 'forevereden-local'
    seed = dict(user_id=user, login=login, tables=data,
                token_aliases={'ItemTokens':'UserItemToken','RandomSeeds':'UserRandomSeed'},
                source_profile_sha256=hashlib.sha256(read('response-plaintext','user_data/pull')).hexdigest(),
                source_index_sha256=client.digest(capture/'index.json'),
                source_scope='starter account, before first battle; imported once; official pending operations excluded')
    headers=dict(line.split(':',1) for line in read('response-headers','user_data/pull').decode('latin1').splitlines() if ':' in line)
    seed['pull_content_type']=headers['Content-Type'].strip()
    if ACTIVE.exists():
        old=json.loads(ACTIVE.read_text())['identity']['seed']
        old_path=client.ROOT/old['path']
        if old_path.resolve().parent != OUT.resolve() or client.digest(old_path) != old['sha256']:
            raise ValueError('Previous seed failed validation')
        previous=json.loads(old_path.read_text(encoding='utf-8'))
        if previous['source_index_sha256'] != seed['source_index_sha256']:
            raise ValueError('Different capture: preserve/migrate the existing seed explicitly')
        seed=previous
        user=seed['user_id']
        data=seed['tables']
    serialized = json.dumps(seed,separators=(',',':'),ensure_ascii=False)
    if str(official_user) in serialized or original_iv in serialized:
        raise ValueError('Official identifier or transport IV remains in the private seed')
    OUT.mkdir(parents=True,exist_ok=True)
    seed_path = OUT / ('seed-' + hashlib.sha256(serialized.encode()).hexdigest()[:16] + '.json')
    if not seed_path.exists():
        seed_path.write_text(serialized+'\n',encoding='utf-8',newline='\n')
    # Original embedded game-body codec constants, not an account/session key.
    sys.path.insert(0,str(client.ROOT/'data/forevereden-evidence'))
    import native_refs as native
    key = bytes(native.readva(0x1704b4f+(c^0x54),1)[0]^0x29 for c in native.readva(0x157e698,32))
    fallback_iv = bytes(native.readva(0x1704bcf+(c^0xf0),1)[0]^0x51 for c in native.readva(0x14e94b0,16))
    codec = OUT/'body-codec-inputs.json'
    client.atomic_json(codec,dict(key_hex=key.hex(),fallback_iv_hex=fallback_iv.hex(),official_lib_md5=hashlib.md5(native.raw).hexdigest(),
        source_lib_sha256=hashlib.sha256(native.raw).hexdigest()))
    checks=[]
    for action in ('matching_user/game_user_id','user/login','user/update_meta','user_data/confirm','user_data/pull'):
        checks.append(dict(action=action,plaintext_hex=read('response-plaintext',action).hex(),
            ciphertext_hex=read('response-wire-body',action).hex(),
            iv_hex=fallback_iv.hex() if action in ('matching_user/game_user_id','user/login') else original_iv.encode().hex()))
    client.atomic_json(OUT/'wire-codec-fixtures.json',checks)
    inventory_path = client.ROOT/'data/forevereden-evidence/network-action-inventory.json'
    inventory = json.loads(inventory_path.read_text())
    active_files = ('tools/forevereden_device_listener.cjs','tools/forevereden_mobile_server.cjs',
        'tools/forevereden_transport.cjs','tools/forevereden_lottery_3_17_0.bin',
        'tools/forevereden_rewards_3_17_0.bin',
        'data/forevereden-evidence/network-action-inventory.json',
        'data/forevereden-evidence/required-packet-semantics.json')
    launcher_files = ('android/forevereden-launcher/app/build.gradle.kts',
        'android/forevereden-launcher/app/src/main/AndroidManifest.xml',
        'android/forevereden-launcher/app/src/main/assets/runtime/main.cjs',
        'android/forevereden-launcher/app/src/main/cpp/native-lib.cpp',
        'android/forevereden-launcher/app/src/main/java/dev/forevereden/launcher/NodeMobileBridge.java',
        'android/forevereden-launcher/app/src/main/kotlin/dev/forevereden/launcher/MainActivity.kt',
        'android/forevereden-launcher/app/src/main/kotlin/dev/forevereden/launcher/NodeListenerService.kt')
    identity=dict(project='ForeverEden',compatibility_version=1,schema_version=1,
        private_client_runtime_id=private['runtime_id'],original_runtime_id=provenance['runtime_id'],
        package=probe.PACKAGE,endpoint=probe.ENDPOINT,
        seed={'path':str(seed_path.relative_to(client.ROOT)),'sha256':client.digest(seed_path)},
        codec={'path':str(codec.relative_to(client.ROOT)),'sha256':client.digest(codec)},
        server={name:client.digest(client.ROOT/name) for name in ('tools/forevereden_server.cjs','tools/forevereden_save.cjs','tools/forevereden_transport.cjs')},
        active_server={name:client.digest(client.ROOT/name) for name in active_files},
        launcher_source={name:client.digest(client.ROOT/name) for name in launcher_files},
        routed_routes=[row['action'] for row in inventory['actions'] if row.get('local_support') == 'routed'],
        non_stub_routes=[row['action'] for row in inventory['actions']
            if row.get('semantic_status') == 'implemented_non_stub'],
        required_untraced_routes=[row['action'] for row in inventory['actions']
            if row.get('semantic_status') == 'untraced_rejected'],
        supported_routes=['matching_user/game_user_id','user/login','user/update_meta','user_data/confirm','user_data/pull','user_data/push','user/migration/status_reset'],
        publisher_migration='disabled',
        content_generation='ec741d3cc2f29b867892b1ed16a7a59b40e3968d',
        content_master_sha256='18c811dabc2a3184c81155a54a234dce64ab23e2eebac4ae1cdfde2ee76386eb',
        limitations=['untraced routes fail closed with HTTP 503; route recognition is not protocol support',
            'operation-backed rewards remain pending until user_data/push supplies the matching id and verifier',
            'ticket-funded lottery is rejected until the exact ticket-row transition is proven',
            'excluded publisher services are not advertised locally'])
    result=dict(runtime_id=client.identity_digest(identity),identity=identity)
    resource_file = OUT.parent/'private-resources/routes.json'
    if resource_file.exists():
        resources = json.loads(resource_file.read_text())
        source_runtime = resources.get('private_client_runtime_id','')
        if (resources['content_generation'] != identity['content_generation'] or len(source_runtime) != 64 or
                any(c not in '0123456789abcdef' for c in source_runtime)):
            raise ValueError('Resource routing identity mismatch')
        identity['resource_routes_source_runtime_id'] = source_runtime
        identity['resource_routes'] = resources['routes']
        result['runtime_id'] = client.identity_digest(identity)
    previous_manifest = json.loads(ACTIVE.read_text()) if ACTIVE.exists() else None
    if migrate_database:
        if previous_manifest is None or previous_manifest['identity']['seed'] != identity['seed']:
            raise ValueError('Migration requires the existing identical seed')
        database = OUT / 'profile.sqlite'
        with sqlite3.connect(database.as_uri()+'?mode=rw', uri=True) as db:
            saved = db.execute('SELECT runtime_id,seed_hash FROM runtime WHERE id=1').fetchone()
            if saved != (previous_manifest['runtime_id'], identity['seed']['sha256']):
                raise ValueError('Database does not match the previous runtime identity')
            if db.execute('PRAGMA user_version').fetchone()[0] != 1:
                raise ValueError('Unsupported database schema')
            backup = OUT / ('before-code-update-'+previous_manifest['runtime_id'][:16]+'.sqlite')
            if backup.exists():
                raise ValueError('Refusing to replace a previous database backup')
            with sqlite3.connect(backup) as destination:
                db.backup(destination)
                if destination.execute('PRAGMA integrity_check').fetchone() != ('ok',):
                    raise ValueError('Database backup integrity failure')
            db.execute('BEGIN IMMEDIATE')
            # Correct the previous startup-only sequence model, preserving all account/profile state.
            db.execute("DELETE FROM replies WHERE action IN ('matching_user/game_user_id','user/login','user/update_meta')")
            seq = max((int(v[0]) for v in db.execute('SELECT sequence FROM replies')), default=-1)
            db.execute('UPDATE account SET last_sequence=? WHERE id=1', (str(seq),))
            db.execute('UPDATE runtime SET runtime_id=? WHERE id=1', (result['runtime_id'],))
            db.commit()
        client.atomic_json(OUT/'code-update.json', dict(previous_runtime=previous_manifest['runtime_id'],
            runtime_id=result['runtime_id'], backup=backup.name, account_and_profile_preserved=True))
    if previous_manifest and previous_manifest['runtime_id'] != result['runtime_id']:
        client.atomic_json(ACTIVE.with_name('previous-local-runtime-identity.json'),previous_manifest)
    client.atomic_json(ACTIVE,result)
    print(json.dumps(dict(runtime_id=result['runtime_id'],table_count=len(data),private_user_id=user)))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,required=True)
    parser.add_argument('--migrate-database',action='store_true',help='Back up and rebind the same-seed startup database; stop the server first')
    args=parser.parse_args()
    prepare(args.capture,args.migrate_database)
