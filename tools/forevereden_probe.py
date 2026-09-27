"""Build a separate, local-only routing probe from the pinned Android APKs.

This is not a game server. Its listener rejects requests with HTTP 503 and
records only route/header names and lengths, never tokens or request bodies.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import struct
import subprocess
import tempfile
import time
import zipfile
import zlib

import forevereden_client as client

PACKAGE = 'games.fed.anothereden'
PORT = 28765
ENDPOINT = f'http://127.0.0.1:{PORT}'
API_FORMAT = (ENDPOINT + '/{}/private').encode()
OUT = client.ROOT / 'data/forevereden-evidence/private-probe'
IDENTITY = client.ROOT / 'forevereden/private-probe-identity.json'
ORIGINAL_URL = b'https://api-{}.another-eden.games'
LOCAL_USER_ID = '193602641768'
XUID_GETTER_OFFSET = 0x3D3DFAC
XUID_GETTER_BEFORE = bytes.fromhex('01200091e00308aae31c1614')
STRING_COPY_OFFSET = 0x42C5340
ELF_PAGE = 0x4000
BILLING_SETUP_OFFSET = 0x10BBE8
BILLING_PURCHASES_OFFSET = 0x10BCA0
BILLING_PURCHASES_CODE_UNITS = 42
BILLING_CATALOG_OFFSET = 0x10CD9C
BILLING_CATALOG_CODE_UNITS = 77
BILLING_COUNTRY_OFFSET = 0x104340
BILLING_COUNTRY_CODE_UNITS = 81
BILLING_ORDER_CATALOG_OFFSET = 0x114638
BILLING_SUBMIT_OFFSET = 0x115AB8
BILLING_SUBMIT_CODE_UNITS = 95
BILLING_REQUEST_URL_OFFSET = 0xF83C8
BILLING_REQUEST_URL_CODE_UNITS = 67
BILLING_SIGNED_RESPONSE_OFFSET = 0xF8B4C
BILLING_LOCAL_URL_STRING_OFFSET = 0x2849A7
BILLING_DEX_SHA256 = 'b79958973f31bebe12b9d271f45c427c5eba1df7d8146ae1ebefd62b58c492d4'


def replace_fixed(data, old, new, count):
    if len(old) != len(new) or data.count(old) != count:
        raise ValueError('Unexpected fixed-width patch input')
    return data.replace(old, new)


def chunks(data):
    if len(data) < 8 or struct.unpack_from('<HHI', data) != (3, 8, len(data)):
        raise ValueError('Unsupported binary manifest')
    at = 8
    result = []
    while at < len(data):
        if at + 8 > len(data):
            raise ValueError('Truncated XML chunk')
        kind, header, size = struct.unpack_from('<HHI', data, at)
        if header < 8 or size < header or at + size > len(data):
            raise ValueError('Invalid XML chunk bounds')
        result.append((kind, bytearray(data[at:at+size])))
        at += size
    return result


def patch_manifest(data, base):
    data = replace_fixed(data, client.PACKAGE.encode('utf-16le'),
                         PACKAGE.encode('utf-16le'), 14 if base else 1)
    if not base:
        chunks(data)
        return data
    parts = chunks(data)
    pool, = [p for kind, p in parts if kind == 1]
    count, styles, flags, start, style_start = struct.unpack_from('<IIIII', pool, 8)
    if styles or style_start or flags & 0x100 or start != 28 + count * 4:
        raise ValueError('Expected unstyled UTF-16 manifest string pool')
    offsets = list(struct.unpack_from(f'<{count}I', pool, 28))
    strings = []
    for offset in offsets:
        at = start + offset
        length, = struct.unpack_from('<H', pool, at)
        if length & 0x8000 or at + 2 + length * 2 + 2 > len(pool):
            raise ValueError('Unexpected manifest string length')
        if pool[at+2+length*2:at+4+length*2] != b'\0\0':
            raise ValueError('Missing string terminator')
        strings.append(pool[at+2:at+2+length*2].decode('utf-16le'))
    if 'usesCleartextTraffic' in strings:
        raise ValueError('Review existing cleartext policy before patching')
    text = bytearray(pool[start:])
    for value in ('usesCleartextTraffic', 'ForeverEden'):
        offsets.append(len(text))
        text += struct.pack('<H', len(value)) + value.encode('utf-16le') + b'\0\0'
    text += b'\0' * (-len(text) % 4)
    new_start = 28 + 4 * len(offsets)
    pool[:] = (struct.pack('<HHIIIIII', 1, 28, new_start + len(text),
                          len(offsets), 0, flags & ~1, new_start, 0)
               + struct.pack(f'<{len(offsets)}I', *offsets) + text)
    resource_map, = [p for kind, p in parts if kind == 0x180]
    ids = list(struct.unpack_from(f'<{(len(resource_map)-8)//4}I', resource_map, 8))
    if len(ids) > count:
        raise ValueError('Invalid resource map')
    ids += [0] * (count + 2 - len(ids))
    ids[count] = 0x010104ec  # Android usesCleartextTraffic attribute.
    resource_map[:] = struct.pack('<HHI', 0x180, 8, 8 + len(ids)*4) + struct.pack(f'<{len(ids)}I', *ids)
    applications = 0
    for kind, part in parts:
        if kind != 0x102:
            continue
        name, = struct.unpack_from('<I', part, 20)
        if strings[name] != 'application':
            continue
        applications += 1
        attr_start, width, n, id_index, class_index, style_index = struct.unpack_from('<HHHHHH', part, 24)
        if attr_start != 20 or width != 20 or id_index or class_index or style_index or len(part) != 36 + n*20:
            raise ValueError('Unexpected application attribute layout')
        attrs = [bytes(part[36+i*20:56+i*20]) for i in range(n)]
        labels = [i for i, a in enumerate(attrs) if ids[struct.unpack_from('<I', a, 4)[0]] == 0x01010001]
        if len(labels) != 1:
            raise ValueError('Expected one application label')
        i = labels[0]
        namespace, label = struct.unpack_from('<II', attrs[i])
        attrs[i] = struct.pack('<IIIHBBI', namespace, label, count+1, 8, 0, 3, count+1)
        attrs.append(struct.pack('<IIIHBBI', namespace, count, 0xffffffff, 8, 0, 0x12, 0xffffffff))
        attrs.sort(key=lambda a: ids[struct.unpack_from('<I', a, 4)[0]])
        part[:] = part[:36] + b''.join(attrs)
        struct.pack_into('<I', part, 4, len(part))
        struct.pack_into('<H', part, 28, n+1)
    if applications != 1:
        raise ValueError('Expected one application element')
    payload = b''.join(part for _, part in parts)
    return struct.pack('<HHI', 3, 8, len(payload)+8) + payload


def patch_local_billing(data):
    """Use local setup, catalog, purchase completion, and billing service."""
    if hashlib.sha256(data).hexdigest() != BILLING_DEX_SHA256:
        raise ValueError('Pinned billing DEX changed')
    data = bytearray(data)
    # Jump to the adapter's existing successful-setup callback.
    data[BILLING_SETUP_OFFSET:BILLING_SETUP_OFFSET + 2] = bytes.fromhex('280a')
    # Report no unfinished Play purchases; later private purchases are server-owned.
    purchases = bytes.fromhex(
        '2200a80912011a02a4157030062a100222016d02701055060100'
        '220294097040bf29120671107f2302000e00')
    size = BILLING_PURCHASES_CODE_UNITS * 2
    data[BILLING_PURCHASES_OFFSET:BILLING_PURCHASES_OFFSET + size] = purchases + bytes(size - len(purchases))
    # e1.onSuccess(Object): this.b.onSuccess(obj); return. The remaining code
    # units stay allocated as NOPs so no DEX table offsets move.
    code = bytes.fromhex('544080147220262250000e00')
    size = BILLING_CATALOG_CODE_UNITS * 2
    data[BILLING_CATALOG_OFFSET:BILLING_CATALOG_OFFSET + size] = code + bytes(size - len(code))
    # PaymentUtil's capability probe needs a Google client only to obtain the
    # store country. The private US catalog already fixes that value.
    country = bytes.fromhex('5440ff101a018a687220262210000e00')
    size = BILLING_COUNTRY_CODE_UNITS * 2
    data[BILLING_COUNTRY_OFFSET:BILLING_COUNTRY_OFFSET + size] = country + bytes(size - len(country))
    # queryOrder must keep using the already-authoritative server product data.
    # Re-querying Play product details dereferences the intentionally absent
    # BillingClient before the order can be created.
    if data[BILLING_ORDER_CATALOG_OFFSET:BILLING_ORDER_CATALOG_OFFSET + 4] != bytes.fromhex('6301e114'):
        raise ValueError('Pinned billing order preflight changed')
    data[BILLING_ORDER_CATALOG_OFFSET:BILLING_ORDER_CATALOG_OFFSET + 4] = bytes.fromhex('12110000')
    # Shop.submit(Activity, Order, listener): the local server owns fulfillment,
    # so complete the SDK callback without launching Play or verifying a receipt.
    submit = bytes.fromhex('12007220262206000e00')
    size = BILLING_SUBMIT_CODE_UNITS * 2
    if data[BILLING_SUBMIT_OFFSET:BILLING_SUBMIT_OFFSET + 6] != bytes.fromhex('71006b230000'):
        raise ValueError('Pinned billing submit method changed')
    data[BILLING_SUBMIT_OFFSET:BILLING_SUBMIT_OFFSET + size] = submit + bytes(size - len(submit))
    # All GREE payment URL builders share RequestUrl. Point that one boundary at
    # the on-device listener and keep unrelated game/CDN routing unchanged.
    old_string = bytes([22]) + b'http://www.example.com\0'
    # Keep both width and lexical position in the sorted DEX string table.
    new_url = b'http://localhost:28765'
    if data[BILLING_LOCAL_URL_STRING_OFFSET:BILLING_LOCAL_URL_STRING_OFFSET + len(old_string)] != old_string:
        raise ValueError('Pinned billing URL string changed')
    data[BILLING_LOCAL_URL_STRING_OFFSET:BILLING_LOCAL_URL_STRING_OFFSET + len(old_string)] = bytes([len(new_url)]) + new_url + b'\0'
    request_url = bytes.fromhex('7010460403001a0063515b30310d0e00')
    size = BILLING_REQUEST_URL_CODE_UNITS * 2
    if data[BILLING_REQUEST_URL_OFFSET:BILLING_REQUEST_URL_OFFSET + 6] != bytes.fromhex('701046040300'):
        raise ValueError('Pinned billing URL constructor changed')
    data[BILLING_REQUEST_URL_OFFSET:BILLING_REQUEST_URL_OFFSET + size] = request_url + bytes(size - len(request_url))
    # Local responses have no official HMAC response signature. Return the
    # already-received response; the request remains confined to loopback.
    if data[BILLING_SIGNED_RESPONSE_OFFSET:BILLING_SIGNED_RESPONSE_OFFSET + 2] != bytes.fromhex('0800'):
        raise ValueError('Pinned signed response validator changed')
    data[BILLING_SIGNED_RESPONSE_OFFSET:BILLING_SIGNED_RESPONSE_OFFSET + 2] = bytes.fromhex('1112')
    data[12:32] = hashlib.sha1(data[32:]).digest()
    struct.pack_into('<I', data, 8, zlib.adler32(data[12:]) & 0xffffffff)
    return bytes(data)


def run(command, **kwargs):
    p = subprocess.run([str(x) for x in command], capture_output=True, timeout=120, **kwargs)
    if p.returncode:
        raise RuntimeError(p.stderr.decode(errors='replace')[-2000:] + p.stdout.decode(errors='replace')[-2000:])
    return p.stdout.decode(errors='replace')


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


def patch_local_identity(data):
    if data[XUID_GETTER_OFFSET:XUID_GETTER_OFFSET + 12] != XUID_GETTER_BEFORE:
        raise ValueError('SDK identity getter changed')
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
    payload[4:8] = struct.pack('<I', 0x91000021 | ((object_address & 0xfff) << 10))
    payload[8:12] = bytes.fromhex('e00308aa')
    payload[12:16] = arm64_branch(virtual_address + 12, STRING_COPY_OFFSET)
    encoded = LOCAL_USER_ID.encode()
    payload[0x100:0x118] = bytes([len(encoded) * 2]) + encoded + b'\0' * (23 - len(encoded))
    data[XUID_GETTER_OFFSET:XUID_GETTER_OFFSET + 4] = arm64_branch(XUID_GETTER_OFFSET, virtual_address)
    struct.pack_into('<IIQQQQQQ', data, phoff + note * phentsize,
                     1, 5, file_offset, virtual_address, virtual_address, ELF_PAGE, ELF_PAGE, ELF_PAGE)
    data.extend(b'\0' * (file_offset - len(data)))
    data.extend(payload)
    return dict(getter_offset=XUID_GETTER_OFFSET, getter_before=XUID_GETTER_BEFORE.hex(),
                local_user_id_sha256=hashlib.sha256(encoded).hexdigest(),
                segment_file_offset=file_offset, segment_virtual_address=virtual_address, segment_bytes=ELF_PAGE)


def build(args):
    baseline, frozen = client.verify()
    OUT.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(OUT).free < 2 * 1024**3:
        raise ValueError('At least 2 GiB host free space required to stage the probe')
    java = args.java_home / 'bin/java.exe'
    signer = args.build_tools / 'lib/apksigner.jar'
    key, password = OUT / 'local-test.p12', OUT / 'local-test.password'
    if key.exists() != password.exists():
        raise ValueError('Incomplete probe signing identity; preserve it for inspection')
    if not key.exists():
        password.write_text(secrets.token_hex(24) + '\n')
        env = os.environ | {'FOREVEREDEN_PROBE_KEY_PASSWORD': password.read_text().strip()}
        run([args.java_home / 'bin/keytool.exe', '-genkeypair', '-keystore', key,
             '-storetype', 'PKCS12', '-alias', 'forevereden-local-probe',
             '-storepass:env', 'FOREVEREDEN_PROBE_KEY_PASSWORD', '-keyalg', 'RSA',
             '-keysize', '2048', '-validity', '3650', '-dname', 'CN=ForeverEden Local Probe'], env=env)
    stage = Path(tempfile.mkdtemp(prefix='.stage-', dir=OUT))
    output, changes, identity_patch, billing_patch = {}, [], None, None
    for apk in client.APKS:
        unsigned, aligned, signed = stage / ('unsigned-' + apk), stage / ('aligned-' + apk), stage / apk
        expected = {}
        with zipfile.ZipFile(frozen / apk) as src, zipfile.ZipFile(unsigned, 'w') as dst:
            for entry in src.infolist():
                name = entry.filename
                if name == 'stamp-cert-sha256' or (name.startswith('META-INF/') and (name == 'META-INF/MANIFEST.MF' or name.endswith(('.RSA', '.DSA', '.EC', '.SF')))):
                    continue
                if entry.file_size > 128 * 1024**2:
                    raise ValueError('APK member exceeds pinned staging bound')
                data = src.read(entry)
                before = hashlib.sha256(data).hexdigest()
                if name == 'AndroidManifest.xml':
                    data = patch_manifest(data, apk == 'games.wfs.anothereden.apk')
                elif name == 'resources.arsc':
                    data = replace_fixed(data, client.PACKAGE.encode('utf-16le'), PACKAGE.encode('utf-16le'), 1)
                elif name == 'lib/arm64-v8a/libapp.so':
                    data = bytearray(replace_fixed(data, ORIGINAL_URL, API_FORMAT, 1))
                    identity_patch = patch_local_identity(data)
                    data = bytes(data)
                elif name == 'classes5.dex':
                    data = patch_local_billing(data)
                    billing_patch = dict(methods=['a0.a(setup)', 'a0.a(restoredPurchases)',
                                                  'e1.onSuccess(catalog)', 'PaymentUtil.a(country)',
                                                  'Shop.r.onSuccess(orderCatalog)', 'Shop.submit(localSuccess)',
                                                  'RequestUrl.<init>(localBase)', 'SignedRequest.onPostRequest(localTrust)'],
                                         behavior='loopback billing service with local catalog and fulfillment')
                after = hashlib.sha256(data).hexdigest()
                if before != after:
                    changes.append(dict(apk=apk, member=name, before_sha256=before, after_sha256=after))
                expected[name] = after
                dst.writestr(entry, data)
        run([args.build_tools / 'zipalign.exe', '-P', '16', '4', unsigned, aligned])
        run([java, '-jar', signer, 'sign', '--min-sdk-version', '24', '--ks', key, '--ks-pass', 'file:' + str(password),
             '--v1-signing-enabled', 'false', '--v2-signing-enabled', 'true',
             '--v3-signing-enabled', 'true', '--v4-signing-enabled', 'false', '--out', signed, aligned])
        verification = run([java, '-jar', signer, 'verify', '--min-sdk-version', '24', '--verbose', '--print-certs', signed])
        cert = re.search(r'Signer #1 certificate SHA-256 digest: ([0-9a-f]+)', verification).group(1)
        tree = run([args.build_tools / 'aapt2.exe', 'dump', 'xmltree', signed, '--file', 'AndroidManifest.xml'])
        if f'A: package="{PACKAGE}"' not in tree:
            raise ValueError('Package rename did not validate')
        if apk == 'games.wfs.anothereden.apk' and not ('usesCleartextTraffic(0x010104ec)=true' in tree and '"ForeverEden"' in tree):
            raise ValueError('Probe label or local HTTP policy did not validate')
        with zipfile.ZipFile(signed) as result:
            actual = {n: hashlib.sha256(result.read(n)).hexdigest() for n in result.namelist()}
        if actual != expected:
            raise ValueError('APK payload changed outside the reviewed patch set')
        output[apk] = dict(bytes=signed.stat().st_size, sha256=client.digest(signed), signer_sha256=cert)
        for temporary in (unsigned, aligned):
            if temporary.resolve().parent != stage.resolve():
                raise ValueError('Temporary path escaped staging directory')
            temporary.unlink()
        print('Verified probe split:', apk, flush=True)
    if len({v['signer_sha256'] for v in output.values()}) != 1:
        raise ValueError('Split signer mismatch')
    identity = dict(project='ForeverEden', purpose='local routing probe, not a gameplay server',
                    parent_runtime_id=baseline['runtime_id'], package=PACKAGE, endpoint=ENDPOINT,
                     api_format=API_FORMAT.decode(),
                     sdk_identity_patch=identity_patch,
                     billing_catalog_patch=billing_patch,
                     apks=output, changes=changes, tool_sha256=client.digest(__file__),
                    removed_signing_metadata=['original JAR signatures', 'original APK signing block', 'stamp-cert-sha256'],
                    server_behavior='HTTP 503 only; game request schemas UNKNOWN',
                     active_mods=['private-billing-catalog'], original_account_data_copied=False)
    rid = client.identity_digest(identity)
    destination = OUT / rid[:16]
    if destination.exists():
        raise ValueError('Probe generation already exists; staged files retained')
    stage.rename(destination)
    result = dict(runtime_id=rid, generation=str(destination.relative_to(client.ROOT)), identity=identity)
    if IDENTITY.exists():
        client.atomic_json(IDENTITY.with_name('previous-private-probe-identity.json'), json.loads(IDENTITY.read_text()))
    client.atomic_json(IDENTITY, result)
    print(json.dumps(dict(runtime_id=rid, generation=result['generation'], package=PACKAGE, endpoint=ENDPOINT)))


def verify_probe():
    baseline, _ = client.verify()
    manifest = json.loads(IDENTITY.read_text(encoding='utf-8'))
    identity = manifest['identity']
    if manifest['runtime_id'] != client.identity_digest(identity):
        raise ValueError('Probe manifest identity mismatch')
    if (identity['parent_runtime_id'] != baseline['runtime_id'] or identity['package'] != PACKAGE
            or identity['endpoint'] != ENDPOINT or identity['api_format'] != API_FORMAT.decode()
            or identity['tool_sha256'] != client.digest(__file__) or set(identity['apks']) != set(client.APKS)):
        raise ValueError('Probe inputs changed; publish a new generation')
    directory = (client.ROOT / manifest['generation']).resolve()
    if directory.parent != OUT.resolve() or directory.name != manifest['runtime_id'][:16]:
        raise ValueError('Probe generation escapes its storage root')
    client.validate_payload(directory, {n: (v['bytes'], v['sha256']) for n,v in identity['apks'].items()})
    return manifest, directory


def device(args):
    manifest, directory = verify_probe()
    if 'arm64-v8a' not in client.adb(args, 'shell', 'getprop', 'ro.product.cpu.abilist').split(','):
        raise ValueError('An ARM64 Android device is required')
    packages = client.adb(args, 'shell', 'pm', 'list', 'packages', PACKAGE).splitlines()
    exists = 'package:' + PACKAGE in packages
    if args.command == 'install':
        if exists:
            raise ValueError('Private package already installed; preserving its data')
        output = client.adb(args, 'install-multiple', *[str(directory / n) for n in client.APKS], timeout=180)
        if 'Success' not in output:
            raise RuntimeError(output)
    elif not exists:
        raise ValueError('Private probe is not installed')
    paths = client.adb(args, 'shell', 'pm', 'path', PACKAGE).splitlines()
    hashes = []
    for line in paths:
        path = line.removeprefix('package:')
        if not re.fullmatch(r'/data/app/[A-Za-z0-9_~+=./-]+\.apk', path):
            raise ValueError('Unexpected installed APK path')
        hashes.append(client.adb(args, 'shell', 'sha256sum', path).split()[0])
    if sorted(hashes) != sorted(v['sha256'] for v in manifest['identity']['apks'].values()):
        raise ValueError('Installed private APK set does not match its identity')
    if args.command == 'launch':
        output = client.adb(args, 'shell', 'am', 'start', '-W', '-n', PACKAGE + '/net.wrightflyer.toybox.AppActivity')
        if 'Status: ok' not in output.splitlines() or 'Error:' in output or 'Exception' in output:
            raise RuntimeError(output)
    print(json.dumps(dict(runtime_id=manifest['runtime_id'], operation=args.command, installed_hashes=sorted(hashes))))


def request_metadata(header):
    """Parse framing only. Unknown routes are hashed; no values or bodies escape."""
    if len(header) > 32768 or not header.endswith(b'\r\n\r\n'):
        raise ValueError('Header bound/termination')
    lines = header[:-4].split(b'\r\n')
    first = re.fullmatch(rb'(GET|POST) (/[^\x00-\x20\x7f-\xff]{0,8191}) HTTP/1\.[01]', lines[0])
    if not first:
        raise ValueError('Request line')
    method, target = first.groups()
    headers = {}
    for line in lines[1:]:
        name, separator, value = line.partition(b':')
        if not separator or not re.fullmatch(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]{1,64}", name):
            raise ValueError('Header name')
        name = name.lower()
        if name in headers or any(c < 32 and c != 9 or c == 127 for c in value):
            raise ValueError('Duplicate or invalid header')
        headers[name] = value.strip()
    if headers.get(b'host') != f'127.0.0.1:{PORT}'.encode() or b'transfer-encoding' in headers:
        raise ValueError('Host or unsupported transfer encoding')
    length = headers.get(b'content-length', b'0')
    if not re.fullmatch(rb'[0-9]{1,7}', length) or int(length) > 1024**2:
        raise ValueError('Body length bound')
    path = target.split(b'?', 1)[0]
    # ponytail: keep only recovered route names; expand when another route is traced.
    known = (b'/us/private/game_client/user/login', b'/us/private/game_client/user_data/pull',
             b'/us/private/game_client/user_data/push')
    return dict(method=method.decode(), route=path.decode() if path in known else None,
                route_sha256=hashlib.sha256(path).hexdigest(), has_query=b'?' in target,
                header_names=sorted(n.decode() for n in headers), body_bytes=int(length))


async def respond(reader, writer, emit, timeout=5):
    metadata, status = {}, 400
    try:
        async with asyncio.timeout(timeout):
            header = await reader.readuntil(b'\r\n\r\n')
            metadata = request_metadata(header)
            await reader.readexactly(metadata['body_bytes'])  # Discard; never log or save.
            status = 503
    except (ValueError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
        pass
    except TimeoutError:
        status = 408
    except ConnectionError:
        status = 499
    finally:
        emit(dict(**metadata, status=status))
        reason = {400:'Bad Request', 408:'Request Timeout', 499:'Client Closed Request', 503:'Service Unavailable'}[status]
        try:
            writer.write(f'HTTP/1.1 {status} {reason}\r\nContent-Length: 0\r\nConnection: close\r\nCache-Control: no-store\r\n\r\n'.encode())
            await asyncio.wait_for(writer.drain(), 1)
        except (ConnectionError, TimeoutError):
            pass
        finally:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), 1)
            except (ConnectionError, TimeoutError):
                pass


async def serve(args):
    manifest, _ = verify_probe()
    if not 1 <= args.seconds <= 600:
        raise ValueError('Probe duration must be 1 to 600 seconds')
    log = OUT / ('routes-' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '.jsonl')
    tasks, count = set(), 0
    with log.open('x', encoding='utf-8') as f:
        def emit(event):
            event.update(runtime_id=manifest['runtime_id'], utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
            line = json.dumps(event)
            f.write(line + '\n')
            f.flush()
            print(line, flush=True)

        async def accept(reader, writer):
            nonlocal count
            if len(tasks) >= 8 or count >= 128:
                writer.close()
                return
            count += 1
            task = asyncio.current_task()
            tasks.add(task)
            try:
                await respond(reader, writer, emit)
            finally:
                tasks.discard(task)

        server = await asyncio.start_server(accept, '127.0.0.1', PORT, limit=32768, backlog=8)
        print(json.dumps(dict(listening=ENDPOINT, seconds=args.seconds, log=str(log))), flush=True)
        async with server:
            await asyncio.sleep(args.seconds)
        # Allow only the existing five-second request deadline to finish.
        if tasks:
            await asyncio.gather(*list(tasks), return_exceptions=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['build', 'verify', 'install', 'launch', 'status', 'serve'])
    parser.add_argument('--java-home', type=Path)
    parser.add_argument('--build-tools', type=Path)
    parser.add_argument('--adb')
    parser.add_argument('--serial')
    parser.add_argument('--seconds', type=int, default=120)
    args = parser.parse_args()
    if args.command == 'build':
        if not args.java_home or not args.build_tools:
            parser.error('build requires --java-home and --build-tools')
        build(args)
    elif args.command == 'serve':
        asyncio.run(serve(args))
    elif args.command == 'verify':
        manifest, _ = verify_probe()
        print(json.dumps(dict(runtime_id=manifest['runtime_id'], verified=True)))
    else:
        if not args.adb or not args.serial:
            parser.error('device operations require --adb and --serial')
        device(args)


if __name__ == '__main__':
    main()
