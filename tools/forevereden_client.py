"""Freeze, verify and launch the one supported original Android build.

No patching, account changes, emulator creation or network redirection occurs.
An explicit ADB serial is mandatory for every device operation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / 'forevereden/runtime-identity.json'
FROZEN = ROOT / 'data/frozen-client'
PACKAGE = 'games.wfs.anothereden'
SOURCE_HASH = '9593f4b56fefe6bb3a9627dd509abd7e23459404050aac6ad6c3600823bd04ff'
CERT_HASH = 'c71f2ed143755c587e2d719a762c87bf5512d134693e4ceee545874dfb4af697'
APKS = {
    'games.wfs.anothereden.apk': (73782867, 'e1aa6314b09172008d2fa9344a416d8607a7bb64bd0365dbe01a4d70cf195afb'),
    'AssetPack1.apk': (113340825, 'b8f9987ef5e194500d36deca9cc0783e2d4fb9d9f9d811541618dc0dddfeb3a8'),
    'config.arm64_v8a.apk': (22951424, '03a0f1ccf66b949bf7b83ec3c700c05cf53ea72cad45aeb4d1cca9832f80ed95'),
    'config.en.apk': (45465, '7dad6b88afd6dc56674e2e239587c6c5240a83580785c438f8f7e7eb6024f7dc'),
    'config.mdpi.apk': (134425, 'dc63d14d505978029b6aebf3acc65f80c2e23ae3533ddf27d1a8d52319541d2d'),
}


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def identity_digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def atomic_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as f:
        json.dump(obj, f, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
        temporary = f.name
    os.replace(temporary, path)


def validate_payload(directory, expected=APKS):
    for name, (size, sha) in expected.items():
        p = directory / name
        if p.is_symlink() or not p.is_file() or p.stat().st_size != size or digest(p) != sha:
            raise ValueError(f'Frozen payload mismatch: {name}')


def freeze(source):
    if digest(source) != SOURCE_HASH:
        raise ValueError('Unsupported XAPK identity; the original 3.17.0 build 699 is required')
    FROZEN.mkdir(parents=True, exist_ok=True)
    generation = 'android-3.17.0-699-' + SOURCE_HASH[:12]
    destination = FROZEN / generation
    if not destination.exists():
        stage = Path(tempfile.mkdtemp(prefix='.staging-', dir=FROZEN))
        with zipfile.ZipFile(source) as z:
            if len(z.namelist()) != len(set(z.namelist())):
                raise ValueError('Duplicate ZIP member')
            for name, (size, _) in APKS.items():
                info = z.getinfo(name)
                if info.file_size != size or info.file_size > 128 * 1024 * 1024 or info.is_dir():
                    raise ValueError(f'Invalid bounded APK member: {name}')
                # Explicit fixed filenames; never extract user-supplied paths.
                with z.open(info) as src, (stage / name).open('xb') as dst:
                    total = 0
                    while chunk := src.read(1024 * 1024):
                        total += len(chunk)
                        if total > size:
                            raise ValueError('ZIP expansion exceeds pinned member size')
                        dst.write(chunk)
        validate_payload(stage)
        os.replace(stage, destination)
    validate_payload(destination)
    members = {}
    for apk in APKS:
        with zipfile.ZipFile(destination / apk) as z:
            for info in z.infolist():
                name = info.filename
                if not (name.endswith('.dex') or name.startswith(('lib/', 'assets/manifests/'))
                        or name in ('assets/lua.zip', 'assets/master/master_data_bundled.enc')):
                    continue
                with z.open(info) as f:
                    sha = hashlib.file_digest(f, 'sha256').hexdigest()
                members[name] = {'apk': apk, 'bytes': info.file_size, 'sha256': sha}
    identity = {
        'project': 'ForeverEden', 'schema': 1,
        'client': {'package': PACKAGE, 'version_name': '3.17.0', 'version_code': 699,
                   'abi': 'arm64-v8a', 'minimum_api': 24, 'source_xapk_sha256': SOURCE_HASH,
                   'signer_certificate_sha256': CERT_HASH,
                   'apks': {n: {'bytes': s, 'sha256': h} for n, (s, h) in APKS.items()},
                   'authoritative_members': members},
        'generation': generation, 'active_mods': [], 'patches': [],
        'launcher': {'path': 'tools/forevereden_client.py', 'sha256': digest(__file__), 'compatibility_version': 1},
        'server': {'schema_version': None, 'compatibility_version': None, 'status': 'NOT_IMPLEMENTED'},
        'protocol': {'status': 'UNKNOWN', 'definitions': None, 'serializers': None},
        'content': {'authority': 'Original APK payloads pinned above', 'downloaded_generation': None,
                    'decoded_gameplay_tables': 'UNKNOWN'},
    }
    result = {'runtime_id': identity_digest(identity), 'identity': identity}
    if ACTIVE.exists():
        previous = json.loads(ACTIVE.read_text(encoding='utf-8'))
        if previous != result:
            atomic_json(ACTIVE.with_name('previous-runtime-identity.json'), previous)
    atomic_json(ACTIVE, result)
    return result


def verify():
    manifest = json.loads(ACTIVE.read_text(encoding='utf-8'))
    identity = manifest['identity']
    if manifest['runtime_id'] != identity_digest(identity):
        raise ValueError('Runtime manifest identity mismatch')
    if identity['client']['source_xapk_sha256'] != SOURCE_HASH or identity['client']['apks'] != {
            n: {'bytes': s, 'sha256': h} for n, (s, h) in APKS.items()}:
        raise ValueError('Unsupported APK set in runtime manifest')
    if identity['launcher']['sha256'] != digest(__file__):
        raise ValueError('Launcher changed; publish and review a new runtime identity')
    directory = (FROZEN / identity['generation']).resolve()
    if directory.parent != FROZEN.resolve() or directory.is_symlink():
        raise ValueError('Frozen generation escapes its storage root')
    validate_payload(directory)
    return manifest, directory


def adb(args, *command, timeout=60):
    if not args.serial or args.serial.startswith('-'):
        raise ValueError('Explicit ADB serial is required')
    p = subprocess.run([args.adb, '-s', args.serial, *command], capture_output=True, timeout=timeout)
    text = p.stdout.decode('utf-8', 'replace').strip()
    if p.returncode:
        raise RuntimeError(p.stderr.decode('utf-8', 'replace').strip() or text
                           or f'ADB {command[0]} failed with exit code {p.returncode}')
    return text


def device(args, command):
    manifest, directory = verify()
    abi = adb(args, 'shell', 'getprop', 'ro.product.cpu.abilist')
    if 'arm64-v8a' not in abi.split(','):
        raise ValueError(f'Device does not report ARM64 ABI: {abi}')
    packages = adb(args, 'shell', 'pm', 'list', 'packages', PACKAGE).splitlines()
    installed = adb(args, 'shell', 'pm', 'path', PACKAGE) if 'package:' + PACKAGE in packages else ''
    if command == 'install':
        if installed:
            raise ValueError('Package already installed: preserving existing app/data; use verify or launch')
        output = adb(args, 'install-multiple', *[str(directory / n) for n in APKS], timeout=180)
        if 'Success' not in output:
            raise RuntimeError(output)
    else:
        if not installed:
            raise ValueError('Frozen client is not installed on this explicit device')
        # On-device byte hashes bind every installed split, not only versionCode.
        paths = [s.removeprefix('package:') for s in installed.splitlines() if s.startswith('package:')]
        hashes = []
        for path in paths:
            if not re.fullmatch(r'/data/app/[A-Za-z0-9_~+=./-]+\.apk', path):
                raise ValueError('Unexpected package-manager APK path')
            hashes.append(adb(args, 'shell', 'sha256sum', path).split()[0])
        if sorted(hashes) != sorted(h for _, h in APKS.values()):
            raise ValueError('Installed APK bytes differ from frozen identity')
        if command == 'launch':
            output = adb(args, 'shell', 'am', 'start', '-W', '-n', PACKAGE + '/net.wrightflyer.toybox.AppActivity')
            if 'Status: ok' not in output.splitlines() or 'Error:' in output or 'Exception' in output:
                raise RuntimeError(output)
        else:
            output = adb(args, 'shell', 'dumpsys', 'package', PACKAGE)
    return {'runtime_id': manifest['runtime_id'], 'serial': args.serial, 'abi': abi, 'operation': command, 'output': output}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['freeze', 'verify', 'install', 'launch', 'status'])
    parser.add_argument('--xapk', type=Path)
    parser.add_argument('--adb', default='adb')
    parser.add_argument('--serial')
    args = parser.parse_args()
    if args.command == 'freeze':
        if not args.xapk:
            parser.error('freeze requires --xapk')
        result = freeze(args.xapk)
    elif args.command == 'verify':
        result, _ = verify()
    else:
        result = device(args, args.command)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
