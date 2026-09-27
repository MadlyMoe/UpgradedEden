"""Build/install the isolated VPN capture client from the pinned private Android generation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import struct
import tempfile
import zipfile

import forevereden_client as client
import forevereden_probe as probe

PACKAGE = 'games.fec.anothereden'
PRIVATE_PACKAGE = probe.PACKAGE
CAPTURE_API = b'http://10.23.0.1:28765/{}/private'
FULL_PULL_OFFSET = 0x30CA098
FULL_PULL_BEFORE = bytes.fromhex('880a40f9')  # ldr x8,[x20,#0x10]
FULL_PULL_AFTER = bytes.fromhex('e8031faa')   # mov x8,xzr
XUID_GETTER_OFFSET = 0x3D3DFAC
XUID_GETTER_BEFORE = bytes.fromhex('01200091e00308aae31c1614')
STRING_COPY_OFFSET = 0x42C5340
STRING_FROM_C_OFFSET = 0x3CE85E8
LIB_HASH_GETTER_OFFSET = 0x3C80DC4
LIB_HASH_GETTER_BEFORE = bytes.fromhex('496200d02941433909010037496200d0')
ELF_PAGE = 0x4000
OUT = client.ROOT / 'data/forevereden-evidence/capture-client'
IDENTITY = client.ROOT / 'forevereden/capture-client-identity.json'
DEFAULT_OFFICIAL_CAPTURE = client.ROOT / 'data/forevereden-evidence/official-login/20260926T065843Z'
ORIGINAL_APPLICATION = b'net.wrightflyer.toybox.ToyboxApplication'
CAPTURE_APPLICATION = b'net.wrightflyer.toybox.CaptureApplicatio'
PUBLISHER_CERTIFICATE = client.ROOT / 'data/apk-investigation/embedded-publisher-certificate.der'


def run(command, **kwargs):
    return probe.run(command, **kwargs)


def official_xuid(capture):
    index = json.loads((capture / 'index.json').read_text())
    values = []
    for entry in index:
        if entry.get('kind') != 'request-plaintext' or entry.get('action') != 'user_data/push':
            continue
        payload = json.loads((capture / entry['file']).read_bytes())
        pending = [payload]
        while pending:
            value = pending.pop()
            if isinstance(value, dict):
                values.extend(str(item) for key, item in value.items() if key == 'userId' and isinstance(item, (str, int)))
                pending.extend(value.values())
            elif isinstance(value, list):
                pending.extend(value)
    unique = set(values)
    if len(unique) != 1 or len(values) < 2:
        raise ValueError('Official push evidence does not contain one consistent SDK identity')
    value = unique.pop()
    if not value.isdigit() or not 10 <= len(value) <= 16:
        raise ValueError('Official SDK identity format changed')
    return value


def official_lib_hash():
    active = json.loads(client.ACTIVE.read_text())
    directory = client.FROZEN / active['identity']['generation']
    client.validate_payload(directory)
    with zipfile.ZipFile(directory / 'config.arm64_v8a.apk') as apk, apk.open('lib/arm64-v8a/libapp.so') as library:
        return hashlib.file_digest(library, 'md5').hexdigest()


def arm64_branch(pc, target):
    distance = target - pc
    if distance % 4 or not -(1 << 27) <= distance < (1 << 27):
        raise ValueError('ARM64 branch target is out of range')
    return struct.pack('<I', 0x14000000 | ((distance >> 2) & 0x3ffffff))


def arm64_adrp(register, pc, target):
    pages = ((target & -4096) - (pc & -4096)) >> 12
    if not -(1 << 20) <= pages < (1 << 20):
        raise ValueError('ARM64 page target is out of range')
    immediate = pages & 0x1fffff
    return struct.pack('<I', 0x90000000 | ((immediate & 3) << 29) | (((immediate >> 2) & 0x7ffff) << 5) | register)


def patch_capture_elf(data, xuid, lib_hash):
    if data[XUID_GETTER_OFFSET:XUID_GETTER_OFFSET + 12] != XUID_GETTER_BEFORE:
        raise ValueError('SDK identity getter changed')
    if data[LIB_HASH_GETTER_OFFSET:LIB_HASH_GETTER_OFFSET + 16] != LIB_HASH_GETTER_BEFORE or not re.fullmatch('[0-9a-f]{32}', lib_hash):
        raise ValueError('Library identity getter changed')
    header = struct.unpack_from('<16sHHIQQQIHHHHHH', data)
    if header[0][:6] != b'\x7fELF\x02\x01' or header[9] != 56:
        raise ValueError('Unexpected libapp ELF format')
    phoff, phentsize, phnum = header[5], header[9], header[10]
    loads, note = [], None
    for index in range(phnum):
        values = struct.unpack_from('<IIQQQQQQ', data, phoff + index * phentsize)
        if values[0] == 1:
            loads.append(values)
        elif values[0] == 4 and values[2:7] == (0x238, 0x238, 0x238, 0xbc, 0xbc):
            note = index
    if len(loads) != 3 or note is None:
        raise ValueError('Pinned libapp program headers changed')
    file_offset = (len(data) + ELF_PAGE - 1) & -ELF_PAGE
    virtual_address = (max(item[3] + item[6] for item in loads) + ELF_PAGE - 1) & -ELF_PAGE
    object_address = virtual_address + 0x100
    payload = bytearray(ELF_PAGE)
    payload[:4] = arm64_adrp(1, virtual_address, object_address)
    payload[4:8] = struct.pack('<I', 0x91000021 | ((object_address & 0xfff) << 10))  # add x1,x1,#0x100
    payload[8:12] = bytes.fromhex('e00308aa')  # mov x0,x8
    payload[12:16] = arm64_branch(virtual_address + 12, STRING_COPY_OFFSET)
    encoded = xuid.encode()
    payload[0x100:0x118] = bytes([len(encoded) * 2]) + encoded + b'\0' * (23 - len(encoded))
    lib_hash_address = virtual_address + 0x180
    payload[0x20:0x24] = arm64_adrp(1, virtual_address + 0x20, lib_hash_address)
    payload[0x24:0x28] = struct.pack('<I', 0x91000021 | ((lib_hash_address & 0xfff) << 10))
    payload[0x28:0x2c] = bytes.fromhex('e00308aa')
    payload[0x2c:0x30] = arm64_branch(virtual_address + 0x2c, STRING_FROM_C_OFFSET)
    payload[0x180:0x1a1] = lib_hash.encode() + b'\0'
    data[XUID_GETTER_OFFSET:XUID_GETTER_OFFSET + 4] = arm64_branch(XUID_GETTER_OFFSET, virtual_address)
    data[LIB_HASH_GETTER_OFFSET:LIB_HASH_GETTER_OFFSET + 4] = arm64_branch(LIB_HASH_GETTER_OFFSET, virtual_address + 0x20)
    struct.pack_into('<IIQQQQQQ', data, phoff + note * phentsize,
                     1, 5, file_offset, virtual_address, virtual_address, ELF_PAGE, ELF_PAGE, ELF_PAGE)
    data.extend(b'\0' * (file_offset - len(data)))
    data.extend(payload)
    return dict(getter_offset=XUID_GETTER_OFFSET, getter_before=XUID_GETTER_BEFORE.hex(),
                sdk_identity_sha256=hashlib.sha256(encoded).hexdigest(), segment_file_offset=file_offset,
                segment_virtual_address=virtual_address, segment_bytes=ELF_PAGE,
                lib_hash_getter_offset=LIB_HASH_GETTER_OFFSET, lib_hash_getter_before=LIB_HASH_GETTER_BEFORE.hex(),
                official_lib_hash_sha256=hashlib.sha256(lib_hash.encode()).hexdigest())


def build_signature_shim(args, stage):
    if client.digest(PUBLISHER_CERTIFICATE) != client.CERT_HASH:
        raise ValueError('Publisher certificate evidence changed')
    android_jar = args.android_sdk / 'platforms/android-36/android.jar'
    d8 = args.build_tools / 'lib/d8.jar'
    if not android_jar.is_file() or not d8.is_file():
        raise ValueError('Android compile dependencies are missing')
    source = client.ROOT / 'tools/CaptureApplicatio.java'
    stub_source = stage / 'stub/net/wrightflyer/toybox/ToyboxApplication.java'
    stub_source.parent.mkdir(parents=True)
    stub_source.write_text('package net.wrightflyer.toybox; public class ToyboxApplication extends android.app.Application {}\n')
    stub_classes, classes, dex = stage / 'stub-classes', stage / 'shim-classes', stage / 'shim-dex'
    for directory in (stub_classes, classes, dex): directory.mkdir()
    javac = args.java_home / 'bin/javac.exe'; java = args.java_home / 'bin/java.exe'
    run([javac, '-source', '8', '-target', '8', '-classpath', android_jar, '-d', stub_classes, stub_source])
    run([javac, '-source', '8', '-target', '8', '-classpath', os.pathsep.join((str(android_jar), str(stub_classes))),
         '-d', classes, source])
    class_file = classes / 'net/wrightflyer/toybox/CaptureApplicatio.class'
    run([java, '-cp', d8, 'com.android.tools.r8.D8', '--min-api', '24', '--lib', android_jar,
         '--classpath', stub_classes, '--output', dex, class_file])
    return dex / 'classes.dex'


def build(args):
    parent, source = probe.verify_probe()
    xuid = official_xuid(args.official_capture)
    lib_hash = official_lib_hash()
    OUT.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(OUT).free < 1024**3:
        raise ValueError('At least 1 GiB host free space is required')
    signer = args.build_tools / 'lib/apksigner.jar'
    java = args.java_home / 'bin/java.exe'
    key, password = OUT / 'capture-local.p12', OUT / 'capture-local.password'
    if key.exists() != password.exists():
        raise ValueError('Incomplete capture signing identity')
    if not key.exists():
        password.write_text(secrets.token_hex(24) + '\n')
        environment = os.environ | {'FOREVEREDEN_CAPTURE_KEY_PASSWORD': password.read_text().strip()}
        run([args.java_home / 'bin/keytool.exe', '-genkeypair', '-keystore', key, '-storetype', 'PKCS12',
             '-alias', 'forevereden-capture', '-storepass:env', 'FOREVEREDEN_CAPTURE_KEY_PASSWORD',
             '-keyalg', 'RSA', '-keysize', '2048', '-validity', '3650', '-dname', 'CN=ForeverEden Capture'], env=environment)
    stage = Path(tempfile.mkdtemp(prefix='.stage-', dir=OUT))
    output, changes = {}, []
    try:
        shim_dex = build_signature_shim(args, stage)
        for apk in client.APKS:
            unsigned, aligned, signed = stage / f'unsigned-{apk}', stage / f'aligned-{apk}', stage / apk
            expected = {}
            with zipfile.ZipFile(source / apk) as src, zipfile.ZipFile(unsigned, 'w') as dst:
                for entry in src.infolist():
                    if entry.filename == 'stamp-cert-sha256' or (entry.filename.startswith('META-INF/') and
                            (entry.filename == 'META-INF/MANIFEST.MF' or entry.filename.endswith(('.RSA','.DSA','.EC','.SF')))):
                        continue
                    if entry.file_size > 128 * 1024**2:
                        raise ValueError('APK member exceeds staging bound')
                    data = src.read(entry); before = hashlib.sha256(data).hexdigest()
                    if entry.filename == 'AndroidManifest.xml':
                        count = 14 if apk == 'games.wfs.anothereden.apk' else 1
                        data = probe.replace_fixed(data, PRIVATE_PACKAGE.encode('utf-16le'), PACKAGE.encode('utf-16le'), count)
                        if apk == 'games.wfs.anothereden.apk':
                            data = probe.replace_fixed(data, ORIGINAL_APPLICATION.decode().encode('utf-16le'),
                                                       CAPTURE_APPLICATION.decode().encode('utf-16le'), 1)
                    elif entry.filename == 'resources.arsc':
                        data = probe.replace_fixed(data, PRIVATE_PACKAGE.encode('utf-16le'), PACKAGE.encode('utf-16le'), 1)
                    elif entry.filename == 'lib/arm64-v8a/libapp.so':
                        data = bytearray(probe.replace_fixed(data, probe.API_FORMAT, CAPTURE_API, 1))
                        if data[FULL_PULL_OFFSET:FULL_PULL_OFFSET+4] != FULL_PULL_BEFORE:
                            raise ValueError('Full-profile patch site changed')
                        data[FULL_PULL_OFFSET:FULL_PULL_OFFSET+4] = FULL_PULL_AFTER
                        xuid_patch = patch_capture_elf(data, xuid, lib_hash)
                        data = bytes(data)
                    after = hashlib.sha256(data).hexdigest()
                    if before != after:
                        changes.append(dict(apk=apk, member=entry.filename, before_sha256=before, after_sha256=after))
                    expected[entry.filename] = after
                    dst.writestr(entry, data)
                if apk == 'games.wfs.anothereden.apk':
                    for name, addition in (('classes6.dex', shim_dex.read_bytes()),
                                           ('assets/forevereden-publisher.der', PUBLISHER_CERTIFICATE.read_bytes())):
                        if name in expected:
                            raise ValueError('Capture shim path already exists')
                        digest = hashlib.sha256(addition).hexdigest()
                        expected[name] = digest
                        changes.append(dict(apk=apk, member=name, before_sha256=None, after_sha256=digest))
                        dst.writestr(name, addition)
            run([args.build_tools / 'zipalign.exe', '-P', '16', '4', unsigned, aligned])
            run([java, '-jar', signer, 'sign', '--min-sdk-version', '24', '--ks', key, '--ks-pass', 'file:' + str(password),
                 '--v1-signing-enabled', 'false', '--v2-signing-enabled', 'true', '--v3-signing-enabled', 'true',
                 '--v4-signing-enabled', 'false', '--out', signed, aligned])
            verification = run([java, '-jar', signer, 'verify', '--min-sdk-version', '24', '--verbose', '--print-certs', signed])
            cert = re.search(r'Signer #1 certificate SHA-256 digest: ([0-9a-f]+)', verification).group(1)
            tree = run([args.build_tools / 'aapt2.exe', 'dump', 'xmltree', signed, '--file', 'AndroidManifest.xml'])
            if (f'A: package="{PACKAGE}"' not in tree or (apk == 'games.wfs.anothereden.apk' and
                    ('usesCleartextTraffic(0x010104ec)=true' not in tree or CAPTURE_APPLICATION.decode() not in tree))):
                raise ValueError('Capture package or cleartext policy did not validate')
            with zipfile.ZipFile(signed) as result:
                actual = {name: hashlib.sha256(result.read(name)).hexdigest() for name in result.namelist()}
            if actual != expected:
                raise ValueError('APK payload changed outside the reviewed patch set')
            output[apk] = dict(bytes=signed.stat().st_size, sha256=client.digest(signed), signer_sha256=cert)
            unsigned.unlink(); aligned.unlink()
            print('Verified capture split:', apk, flush=True)
        if len({value['signer_sha256'] for value in output.values()}) != 1:
            raise ValueError('Split signer mismatch')
        identity = dict(project='ForeverEden', purpose='app-scoped official profile capture',
                        parent_private_runtime_id=parent['runtime_id'], package=PACKAGE,
                        endpoint='http://10.23.0.1:28765', api_format=CAPTURE_API.decode(),
                        full_profile_patch=dict(offset=FULL_PULL_OFFSET, before=FULL_PULL_BEFORE.hex(), after=FULL_PULL_AFTER.hex()),
                        sdk_identity_patch=xuid_patch,
                        local_signature_shim=dict(application=CAPTURE_APPLICATION.decode(), publisher_certificate_sha256=client.CERT_HASH,
                                                  method='legacy GET_SIGNATURES substitution from supplied mod design'),
                        apks=output, changes=changes, signer_isolated=True,
                        official_authorization_persistence='forbidden by launcher proxy')
        runtime_id = client.identity_digest(identity)
        destination = OUT / runtime_id[:16]
        if destination.exists():
            raise ValueError('Capture generation already exists; staged files retained')
        stage.rename(destination)
        result = dict(runtime_id=runtime_id, generation=str(destination.relative_to(client.ROOT)), identity=identity)
        client.atomic_json(IDENTITY, result)
        print(json.dumps(dict(runtime_id=runtime_id, package=PACKAGE, generation=result['generation'])))
    except Exception:
        raise


def verify():
    parent, _ = probe.verify_probe()
    manifest = json.loads(IDENTITY.read_text())
    identity = manifest['identity']
    if manifest['runtime_id'] != client.identity_digest(identity) or identity['parent_private_runtime_id'] != parent['runtime_id'] or identity['package'] != PACKAGE:
        raise ValueError('Capture client identity mismatch')
    directory = (client.ROOT / manifest['generation']).resolve()
    if directory.parent != OUT.resolve() or directory.name != manifest['runtime_id'][:16]:
        raise ValueError('Capture generation path escaped')
    client.validate_payload(directory, {name: (value['bytes'], value['sha256']) for name, value in identity['apks'].items()})
    return manifest, directory


def device(args):
    manifest, directory = verify()
    exists = 'package:' + PACKAGE in client.adb(args, 'shell', 'pm', 'list', 'packages', PACKAGE).splitlines()
    if args.command == 'install':
        if exists:
            raise ValueError('Capture package already installed; preserving its data')
        result = client.adb(args, 'install-multiple', *[str(directory / name) for name in client.APKS], timeout=180)
        if 'Success' not in result:
            raise RuntimeError(result)
    elif not exists:
        raise ValueError('Capture package is not installed')
    print(json.dumps(dict(runtime_id=manifest['runtime_id'], operation=args.command, installed=True)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('build','install','status'))
    parser.add_argument('--java-home', type=Path, default=Path(os.environ.get('JAVA_HOME', '')))
    parser.add_argument('--build-tools', type=Path, default=Path(r'C:\Main\Productivity\Coding\Android\Sdk\build-tools\36.0.0'))
    parser.add_argument('--android-sdk', type=Path, default=Path(r'C:\Main\Productivity\Coding\Android\Sdk'))
    parser.add_argument('--official-capture', type=Path, default=DEFAULT_OFFICIAL_CAPTURE)
    parser.add_argument('--adb', default=r'C:\Main\Productivity\Coding\Android\Sdk\platform-tools\adb.exe')
    parser.add_argument('--serial', default='10.0.2.207:5555')
    arguments = parser.parse_args()
    build(arguments) if arguments.command == 'build' else device(arguments)
