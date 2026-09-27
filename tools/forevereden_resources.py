"""Reuse verified original resources through Android OverlayFS metadata copies.

Both games must be stopped. Original resource bytes/owners stay unchanged;
private resource writes go to a separate upper layer. Account data is excluded.
Mounts last until explicitly removed or the guest restarts.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
from types import SimpleNamespace

import android_preseed as content
import forevereden_client as client
import forevereden_probe as probe

ORIGINAL = content.ROOT
PRIVATE = f'/data/user/0/{probe.PACKAGE}/files/contents'
LAYERS = '/data/local/tmp/forevereden-resources-' + content.VERSION[:16]
OUT = client.ROOT/'data/forevereden-evidence/private-resources'
Q = shlex.quote


def parse_inventory(text):
    result = {}
    for line in text.splitlines():
        digest, name = line.split('  ', 1)
        if not name.startswith('./') or not re.fullmatch('[0-9a-f]{32}', digest):
            raise ValueError('Unexpected resource inventory')
        name = content.safe_path(name[2:])
        if name in result:
            raise ValueError('Duplicate resource path')
        result[name] = digest
    return result


def verify_inventory(inventory, expected):
    missing = [r['path'] for r in expected if inventory.get(r['path']) != r['md5']]
    if missing:
        raise ValueError(f'{len(missing)} missing or changed original assets')


def verify_preload(record, runtime_id, phases, rows, pins, owner):
    if (record.get('complete') is not True or record.get('package') != probe.PACKAGE or
            record.get('private_client_runtime_id') != runtime_id or record.get('version') != content.VERSION or
            record.get('phases') != phases or record.get('manifest_sha256') != pins or
            record.get('verified_files') != len(rows) or record.get('verified_bytes') != sum(r['size'] for r in rows) or
            record.get('owner') != owner or not re.fullmatch(r'10\d{3}:10\d{3}', owner)):
        raise ValueError('Permanent private preload has not been fully verified')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['mount','route','unmount','status'])
    parser.add_argument('--adb', default='adb')
    parser.add_argument('--serial', required=True)
    parser.add_argument('--phases', type=int, nargs='+', choices=range(1,17), default=[1,2])
    parser.add_argument('--permanent', action='store_true', help='Route a verified permanent private preload instead of an overlay')
    args = parser.parse_args()
    if args.permanent and args.command != 'route':
        parser.error('--permanent is only used with route')
    phases = sorted(set(args.phases))
    shell = lambda command, timeout=120: client.adb(args,'shell',command,timeout=timeout)
    if args.command == 'status':
        print(shell(f'cat /proc/mounts | grep {Q(PRIVATE)} || true'))
        return
    if shell('id -u') != '0':
        raise ValueError('Temporary root access in the task emulator is required')
    if shell(f'pidof {probe.PACKAGE} {client.PACKAGE} || true'):
        raise ValueError('Stop both games before changing resource mounts')
    mounts = shell('cat /proc/mounts').splitlines()
    def mount_line(target):
        return [line for line in mounts if line.split()[1] == target]
    if args.command == 'unmount':
        for phase in reversed(phases):
            target = f'{PRIVATE}/{phase}'
            found = mount_line(target)
            if len(found) != 1 or found[0].split()[2] != 'overlay' or f'upperdir={LAYERS}/{phase}/upper' not in found[0].split(','):
                raise ValueError('Refusing to unmount an unknown or absent filesystem')
            shell(f'umount {Q(target)}')
        print(json.dumps(dict(unmounted_phases=phases,private_files_and_originals_preserved=True)))
        return
    if args.command == 'route':
        private_identity, _ = probe.verify_probe()
        if args.permanent:
            record = json.loads((OUT.parent/'private-preseed/verification.json').read_text())
            rows, pins = content.assets(client.ROOT/'data/forevereden-evidence/android-download-before')
            verify_preload(record,private_identity['runtime_id'],phases,rows,pins,shell(f'stat -c %u:%g {PRIVATE}'))
            if shell(f'find {Q(PRIVATE)} -type l'):
                raise ValueError('Private resource symlinks are unsupported')
        else:
            record = json.loads((OUT/'mount.json').read_text())
        if not args.permanent and (record['private_client_runtime_id'] != private_identity['runtime_id'] or
                record['content_generation'] != content.VERSION or record['phases'] != phases):
            raise ValueError('Resource mount identity mismatch')
        routes = {}
        for phase in phases:
            target = f'{PRIVATE}/{phase}'
            found = mount_line(target)
            if args.permanent and found:
                raise ValueError('Permanent resources must not be hidden by a mount')
            if not args.permanent and (len(found) != 1 or f'upperdir={LAYERS}/{phase}/upper' not in found[0].split(',')):
                raise ValueError('Only the verified private overlay may be rewritten')
            for kind in ('project','version'):
                raw = shell(f'cat {ORIGINAL}/{phase}/{kind}.manifest')
                value = json.loads(raw)
                if value['version'] != content.VERSION or value['packageUrl'] != content.CDN:
                    raise ValueError('Unexpected source manifest identity')
                if not args.permanent and kind == 'project' and hashlib.sha256(raw.encode()).hexdigest() != record['source_manifest_sha256'][str(phase)]:
                    raise ValueError('Original completed manifest changed')
                for field, name in [('remoteVersionUrl','version'),('remoteManifestUrl','project')]:
                    value[field] = f'{probe.ENDPOINT}/content/{content.VERSION}/{name}.manifest.{phase}'
                local = OUT/f'{kind}.manifest.{phase}.json'
                client.atomic_json(local,value)
                routes[f'/content/{content.VERSION}/{kind}.manifest.{phase}'] = dict(
                    path=local.relative_to(client.ROOT).as_posix(),bytes=local.stat().st_size,sha256=client.digest(local))
                temp = f'{target}/{kind}.manifest.forevereden-part'
                client.adb(args,'push',str(local),temp,timeout=60)
                if shell(f'sha256sum {temp}').split()[0] != client.digest(local):
                    raise ValueError('Private manifest transfer mismatch')
                shell(f'chown {record["owner"]} {temp} && chmod 600 {temp} && mv {temp} {target}/{kind}.manifest')
        result = dict(private_client_runtime_id=private_identity['runtime_id'],content_generation=content.VERSION,
            routes=routes,tool_sha256=client.digest(__file__),resource_bytes_changed=False,
            storage='permanent-private-files' if args.permanent else 'temporary-overlay',
            compatibility_change='Only private resource-manifest version/project URLs point to the local immutable generation')
        client.atomic_json(OUT/'routes.json',result)
        print(json.dumps(dict(published_resource_routes=len(routes),resource_bytes_changed=False)))
        return
    client.device(args,'status')
    probe.device(SimpleNamespace(adb=args.adb,serial=args.serial,command='status'))
    private_identity, _ = probe.verify_probe()
    owner = shell(f'stat -c %u:%g {Q(PRIVATE)}')
    original_owner = shell(f'stat -c %u:%g {Q(ORIGINAL)}')
    if not re.fullmatch(r'10\d{3}:10\d{3}',owner) or owner == original_owner:
        raise ValueError('Unexpected resource ownership boundary')
    if shell(f'find {Q(ORIGINAL)} -type l'):
        raise ValueError('Original resource symlinks are unsupported')
    all_rows, pins = content.assets(client.ROOT/'data/forevereden-evidence/android-download-before')
    expected = [r for r in all_rows if int(r['path'].split('/')[0]) in phases]
    previous = json.loads((OUT/'mount.json').read_text()) if (OUT/'mount.json').exists() else None
    resuming = previous is not None
    if resuming and (previous['private_client_runtime_id'] != private_identity['runtime_id'] or
                     previous['content_generation'] != content.VERSION or previous['phases'] != phases or
                     previous['owner'] != owner or previous['layers'] != LAYERS):
        raise ValueError('Preserved resource layers belong to another identity')
    reserve = 256*1024**2 if resuming else 1024**3
    if shutil.disk_usage(client.ROOT).free < reserve + (0 if resuming else len(expected)*8192):
        raise ValueError('Insufficient host space for bounded metadata copies plus 1 GiB reserve')
    OUT.mkdir(exist_ok=True)
    before, metadata_before, manifests = {}, {}, {}
    for phase in phases:
        if mount_line(f'{PRIVATE}/{phase}'):
            raise ValueError('Target already mounted; inspect or unmount explicitly')
        prefix = f'{ORIGINAL}/{phase}'
        top = shell(f'ls -1 {Q(prefix)}').splitlines()
        if not set(top) <= {'files','lua','master','manifests','project.manifest','version.manifest'}:
            raise ValueError('Unexpected source content; account/cache sharing is forbidden')
        raw = shell(f'cat {Q(prefix)}/project.manifest',timeout=60)
        manifest = json.loads(raw)
        if manifest['version'] != content.VERSION or manifest['packageUrl'] != content.CDN:
            raise ValueError('Original completed manifest generation mismatch')
        manifests[str(phase)] = hashlib.sha256(raw.encode()).hexdigest()
        inventory = shell(f'cd {Q(prefix)} && find . -type f -print0 | xargs -0 -n 128 md5sum',timeout=300)
        before[phase] = inventory
        metadata_before[phase] = shell(f'cd {Q(prefix)} && find . -type f -print0 | xargs -0 -n 128 stat -c "%u:%g:%a:%s %n"',timeout=120)
        parsed = {f'{phase}/{k}':v for k,v in parse_inventory(inventory).items()}
        verify_inventory(parsed,[r for r in expected if r['path'].startswith(f'{phase}/')])
        print(json.dumps(dict(phase=phase,verified_original_files=len(parsed))),flush=True)
    mounted = []
    try:
        for phase in phases:
            if shutil.disk_usage(client.ROOT).free < reserve:
                raise ValueError('Host reserve reached; original files preserved')
            layer, target = f'{LAYERS}/{phase}',f'{PRIVATE}/{phase}'
            if resuming:
                shell(f'test -d {Q(layer)}/upper && test -d {Q(layer)}/work && test -z "$(find {Q(layer)} -type l)"')
                if manifests[str(phase)] != previous['source_manifest_sha256'][str(phase)]:
                    raise ValueError('Preserved lower generation changed')
            else:
                shell(f'test ! -e {Q(layer)} && mkdir -p {Q(layer)}/upper {Q(layer)}/work')
            shell(f'mount -t overlay overlay -o lowerdir={ORIGINAL}/{phase},upperdir={layer}/upper,workdir={layer}/work,metacopy=on,index=off,redirect_dir=on {target}')
            mounted.append(phase)
            observed = shell(f'cat /proc/mounts | grep " {target} "')
            if 'metacopy=on' not in observed:
                raise ValueError('Metadata-only copy-up was not enabled')
            shell(f'chown -R {owner} {Q(target)}',timeout=300)
            # The upper layer must contain metadata only before the game is launched.
            allocated = int(shell(f'du -sk {Q(layer)}').split()[0])*1024
            if allocated > (len(parse_inventory(before[phase]))+20000)*8192:
                raise ValueError('Unexpected resource data copy')
            original_stat = shell(f'cd {Q(ORIGINAL)}/{phase} && find . -type f -print0 | xargs -0 -n 128 stat -c "%u:%g:%a:%s %n"',timeout=120)
            if original_stat != metadata_before[phase]:
                raise ValueError('Original resource metadata changed')
            original_hashes = shell(f'cd {Q(ORIGINAL)}/{phase} && find . -type f -print0 | xargs -0 -n 128 md5sum',timeout=300)
            if original_hashes != before[phase]:
                raise ValueError('Original resource bytes changed')
            merged = parse_inventory(shell(f'cd {Q(target)} && find . -type f -print0 | xargs -0 -n 128 md5sum',timeout=300))
            verify_inventory({f'{phase}/{k}':v for k,v in merged.items()},
                             [r for r in expected if r['path'].startswith(f'{phase}/')])
            print(json.dumps(dict(phase=phase,mounted=True,upper_allocated_bytes=allocated,original_unchanged=True)),flush=True)
    except BaseException:
        for phase in reversed(mounted):
            shell(f'umount {PRIVATE}/{phase}')
        raise
    result = dict(private_client_runtime_id=private_identity['runtime_id'],content_generation=content.VERSION,
        phases=phases,owner=owner,original_owner=original_owner,source_manifest_sha256=manifests,
        expected_manifest_sha256=pins,verified_asset_count=len(expected),original_bytes_and_metadata_unchanged=True,
        tool_sha256=client.digest(__file__),kernel=shell('uname -r'),layers=LAYERS,
        limitation='Local emulator only; keep original game stopped; remount after guest restart; no account data shared')
    client.atomic_json(OUT/'mount.json',result)
    print(json.dumps(result | {'expected_manifest_sha256':'recorded'}),flush=True)


if __name__ == '__main__':
    main()
