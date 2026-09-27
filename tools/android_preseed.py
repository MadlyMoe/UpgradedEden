"""Preload exact-manifest assets using Android's existing parallel curl.

The game must stay stopped. Files are checked before atomic publication;
updater manifests and account data are never rewritten. No APK modification.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import time
from urllib.parse import quote

from forevereden_client import device

PACKAGE = 'games.wfs.anothereden'
ROOT = f'/data/user/0/{PACKAGE}/files/contents'
REMOTE = '/data/local/tmp/forevereden-download'
CDN = 'https://cdn-another-eden.akamaized.net/us'
VERSION = 'ec741d3cc2f29b867892b1ed16a7a59b40e3968d'
Q = shlex.quote


def safe_path(value):
    if (not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_./@+ -]+', value)
            or value.startswith('/') or any(p in ('', '.', '..') for p in value.split('/'))):
        raise ValueError(f'Unsafe asset path: {value!r}')
    return value


def assets(folder, phases=range(1, 17), region='us'):
    cdn = f'https://cdn-another-eden.akamaized.net/{region}'
    result, pins = [], {}
    for phase in phases:
        path = folder / f'{phase}-project.manifest.temp.json'
        raw = path.read_bytes()
        pins[path.name] = hashlib.sha256(raw).hexdigest()
        m = json.loads(raw)
        if (m['version'] != VERSION or m['packageUrl'] != cdn or
                m['remoteManifestUrl'] != f'{cdn}/{VERSION}/pkm/production-global-{region}/project.manifest.{phase}'):
            raise ValueError('Unexpected content identity')
        for key, value in m['assets'].items():
            key, url_path = safe_path(key), safe_path(value['path'])
            if key.split('/')[0] not in ('files', 'lua', 'master', 'manifests'):
                raise ValueError('Unexpected asset root')
            if not re.fullmatch(r'[0-9a-f]{32}', value['md5']):
                raise ValueError('Invalid MD5')
            size = value['size']
            if not isinstance(size, int) or not 0 < size <= 512 * 1024 * 1024:
                raise ValueError('Invalid asset size')
            # These manifests also list Steam movies; stock Android phase 1
            # completed without them. Preserve Android's separate files/movie.
            if key.startswith('files/movie_pc/'):
                continue
            result.append(dict(path=f'{phase}/{key}', url=cdn + '/' + url_path,
                               size=size, md5=value['md5']))
    return result, pins


def batches(rows):
    batch, size = [], 0
    for row in rows:
        if batch and (len(batch) >= 512 or size + row['size'] > 96 * 1024 * 1024):
            yield batch
            batch, size = [], 0
        batch.append(row)
        size += row['size']
    if batch:
        yield batch


def transfer_url(row, original):
    return ('file://' + quote(ROOT + '/' + safe_path(row['path']), safe='/')
            if original.get(row['path']) == row['md5'] else row['url'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adb', default='adb')
    parser.add_argument('--serial', required=True)
    parser.add_argument('--manifest-dir', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=24, choices=range(1, 65))
    parser.add_argument('--phases', type=int, nargs='+', choices=range(1, 17), default=range(1, 17))
    parser.add_argument('--reserve-gib', type=int, default=3, choices=range(2, 17))
    parser.add_argument('--region', choices=('us', 'ap'), default='us')
    parser.add_argument('--limit-batches', type=int)
    parser.add_argument('--private', action='store_true', help='Preload ForeverEden, reusing matching original assets before the CDN')
    args = parser.parse_args()
    reserve = args.reserve_gib * 1024**3
    # Reuse the launcher: verify all five installed APK hashes before touching
    # resources, rather than trusting only a package name or version code.
    private_identity = None
    if args.private:
        import forevereden_probe as probe
        from types import SimpleNamespace
        probe.device(SimpleNamespace(adb=args.adb, serial=args.serial, command='status'))
        private_identity = json.loads(probe.IDENTITY.read_text())['runtime_id']
    else:
        device(args, 'status')
    package = 'games.fed.anothereden' if args.private else PACKAGE
    root = f'/data/user/0/{package}/files/contents'
    remote = REMOTE + ('-private' if args.private else '')
    adb = [args.adb, '-s', args.serial]
    output = args.manifest_dir.parent / (('private-preseed' if args.private else 'android-preseed')
                                         + (f'-{args.region}' if args.region != 'us' else ''))
    output.mkdir(exist_ok=True)

    def shell(command, timeout=120):
        p = subprocess.run(adb + ['shell', command], capture_output=True, timeout=timeout)
        if p.returncode:
            raise RuntimeError(p.stderr.decode(errors='replace')[-1000:] + p.stdout.decode(errors='replace')[-1000:])
        return p.stdout.decode().strip()

    def stopped():
        if shell(f'pidof {package}' + (f' {PACKAGE}' if args.private else '') + ' || true'):
            raise RuntimeError('Game is running; no resource writes allowed')

    stopped()
    if shell('id -u') != '0':
        raise RuntimeError('Isolated emulator root access is required')
    if args.private and any(line.split()[1].startswith(root + '/') for line in shell('cat /proc/mounts').splitlines()):
        raise RuntimeError('Unmount the temporary private resource views before permanent preloading')
    owner = shell(f'stat -c %u:%g {root}')
    if not re.fullmatch(r'10[0-9]{3}:10[0-9]{3}', owner):
        raise RuntimeError('Unexpected app-data owner')
    if shell(f'find {root} -type l'):
        raise RuntimeError('Symlinks in resource tree are not supported')
    rows, pins = assets(args.manifest_dir, args.phases, args.region)
    inventory = shell(f'cd {root} && find . -type f -print0 | xargs -0 -n 128 md5sum', 300)
    (output / 'inventory-before.md5').write_text(inventory + '\n')
    existing = {}
    for line in inventory.splitlines():
        md5, path = line.split('  ', 1)
        existing[path.removeprefix('./')] = md5
    needed = [r for r in rows if existing.get(r['path']) != r['md5']]
    original = {}
    if args.private:
        if shell(f'find {ROOT} -type l'):
            raise RuntimeError('Original resource symlinks are unsupported')
        source = shell(f'cd {ROOT} && find . -type f -print0 | xargs -0 -n 128 md5sum', 300)
        for line in source.splitlines():
            digest, name = line.split('  ', 1)
            original[name.removeprefix('./')] = digest
    # Preserve nonmatching existing files; do not turn this asset downloader
    # into a repair/delete tool. The stock client can handle those separately.
    conflicts = [r['path'] for r in needed if r['path'] in existing]
    if conflicts:
        raise RuntimeError(f'{len(conflicts)} existing assets differ; no files replaced')
    total = sum(r['size'] for r in needed)
    if shutil.disk_usage(output).free < total + reserve:
        raise RuntimeError(f'Insufficient host space for emulator disk growth plus {args.reserve_gib} GiB reserve')
    plan = dict(version=VERSION, region=args.region, serial=args.serial, owner=owner, manifest_sha256=pins,
                required_files=len(needed), required_bytes=total, workers=args.workers,
                host_reserve_bytes=reserve,package=package,private_client_runtime_id=private_identity,
                reusable_files=sum(original.get(r['path']) == r['md5'] for r in needed),
                cdn_bytes=sum(r['size'] for r in needed if original.get(r['path']) != r['md5']))
    (output / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    print(json.dumps(plan | {'manifest_sha256': 'recorded in plan.json'}), flush=True)
    shell(f'mkdir -p {remote}')
    done, received, start = 0, 0, time.monotonic()
    journal = output / 'batches.jsonl'
    for index, batch in enumerate(batches(needed), 1):
        if args.limit_batches and index > args.limit_batches:
            break
        stopped()
        if shutil.disk_usage(output).free < reserve:
            raise RuntimeError('Host storage reserve reached; completed assets preserved')
        config, checks, publish = [], [], ['set -eu', f'cd {Q(root)}',
                                         f'test -z "$(pidof {package} || true)"']
        parents, temps, renames = set(), [], []
        for row in batch:
            dest = row['path']
            temp = dest + '.forevereden-part'
            config += [f'url = "{transfer_url(row, original)}"', f'output = "{root}/{temp}"']
            checks.append(f'{row["md5"]}  {temp}')
            temps.append(temp)
            for parent in PurePosixPath(dest).parents:
                if str(parent) != '.':
                    parents.add(str(parent))
            # Refuse to overwrite a target created since inventory.
            publish += [f'test ! -e {Q(dest)}']
            # Android mksh's rename builtin avoids one process per tiny asset.
            renames.append(f'rename {Q(temp)} {Q(dest)}')
        for offset in range(0, len(temps), 100):
            group = temps[offset:offset + 100]
            publish += [f'chown {owner} ' + ' '.join(map(Q, group)),
                        'chmod 600 ' + ' '.join(map(Q, group))]
        publish += renames
        for offset in range(0, len(parents), 100):
            group = sorted(parents)[offset:offset + 100]
            publish += [f'chown {owner} ' + ' '.join(map(Q, group)),
                        'chmod 700 ' + ' '.join(map(Q, group))]
        phases = sorted({r['path'].split('/')[0] for r in batch})
        publish += ['restorecon -R ' + ' '.join(map(Q, phases)), 'echo FOREVEREDEN_PUBLISHED']
        for name, content in [('batch.curl', '\n'.join(config)),
                              ('batch.md5', '\n'.join(checks)),
                              ('publish.sh', '\n'.join(publish))]:
            local = output / name
            local.write_text(content + '\n', encoding='utf-8', newline='\n')
            subprocess.run(adb + ['push', str(local), remote + '/' + name],
                           check=True, capture_output=True, timeout=30)
        t = time.monotonic()
        shell(f'curl --fail --silent --show-error --parallel --parallel-immediate '
              f'--parallel-max {args.workers} --retry 3 --connect-timeout 15 --max-time 300 '
              f'--create-dirs --config {remote}/batch.curl', 1200)
        proof = shell(f'cd {root} && md5sum -c {remote}/batch.md5 && echo FOREVEREDEN_VERIFIED', 180)
        if not proof.endswith('FOREVEREDEN_VERIFIED'):
            raise RuntimeError('Batch hash verification did not finish; temporary files retained')
        stopped()
        if not shell(f'sh {remote}/publish.sh', 180).endswith('FOREVEREDEN_PUBLISHED'):
            raise RuntimeError('Batch publication incomplete; inspect journal and files')
        done += len(batch)
        received += sum(r['size'] for r in batch)
        row = dict(batch=index, files=done, bytes=received, total_bytes=total,
                   batch_seconds=round(time.monotonic()-t, 2),
                   elapsed_seconds=round(time.monotonic()-start, 2),
                   host_free_bytes=shutil.disk_usage(output).free)
        with journal.open('a', encoding='utf-8') as f:
            f.write(json.dumps(row) + '\n')
        print(json.dumps(row), flush=True)
    if done == len(needed):
        stopped()
        final = shell(f'cd {root} && find . -type f -print0 | xargs -0 -n 128 md5sum', 300)
        inventory = {name.removeprefix('./'): digest for digest,name in
                     (line.split('  ',1) for line in final.splitlines())}
        if any(inventory.get(r['path']) != r['md5'] for r in rows):
            raise RuntimeError('Final complete-cache verification failed')
        result = dict(plan, complete=True, verified_files=len(rows), verified_bytes=sum(r['size'] for r in rows),
                      phases=list(range(1,17)), tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        (output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print('VERIFIED_AND_PUBLISHED', done, received, flush=True)


if __name__ == '__main__':
    main()
