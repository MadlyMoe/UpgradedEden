"""Small offline checks against the pinned local client; no Android mutation."""
import struct
import asyncio
import hashlib
import json
import zipfile
import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import forevereden_client as client
import forevereden_probe as probe
from forevereden_probe import API_FORMAT, BILLING_CATALOG_CODE_UNITS, BILLING_CATALOG_OFFSET, BILLING_COUNTRY_CODE_UNITS, BILLING_COUNTRY_OFFSET, BILLING_LOCAL_URL_STRING_OFFSET, BILLING_ORDER_CATALOG_OFFSET, BILLING_PURCHASES_CODE_UNITS, BILLING_PURCHASES_OFFSET, BILLING_REQUEST_URL_CODE_UNITS, BILLING_REQUEST_URL_OFFSET, BILLING_SETUP_OFFSET, BILLING_SIGNED_RESPONSE_OFFSET, BILLING_SUBMIT_CODE_UNITS, BILLING_SUBMIT_OFFSET, ORIGINAL_URL, PACKAGE, chunks, patch_local_billing, patch_manifest, replace_fixed, request_metadata, respond

assert len(API_FORMAT) == len(ORIGINAL_URL) and b'\0' not in API_FORMAT
assert API_FORMAT.decode().format('us') == 'http://127.0.0.1:28765/us/private'
_, frozen = client.verify()
for apk in client.APKS:
    with zipfile.ZipFile(frozen / apk) as z:
        original = z.read('AndroidManifest.xml')
    patched = patch_manifest(original, apk == 'games.wfs.anothereden.apk')
    assert client.PACKAGE.encode('utf-16le') not in patched
    assert PACKAGE.encode('utf-16le') in patched
    assert chunks(patched)
    if apk == 'games.wfs.anothereden.apk':
        assert 'usesCleartextTraffic'.encode('utf-16le') in patched
        assert 'ForeverEden'.encode('utf-16le') in patched
    try:
        patch_manifest(patched, apk == 'games.wfs.anothereden.apk')
        raise AssertionError('Double patch accepted')
    except ValueError:
        pass
for damaged in (b'', b'\x03\x00\x08\x00\xff\xff\xff\x7f', struct.pack('<HHIHHI',3,8,16,1,8,0)):
    try:
        chunks(damaged)
        raise AssertionError('Malformed XML accepted')
    except ValueError:
        pass
for old,new,count in ((b'a',b'longer',1),(b'missing',b'unknown',1),(b'a',b'b',2)):
    try:
        replace_fixed(b'a',old,new,count)
        raise AssertionError('Unexpected patch input accepted')
    except ValueError:
        pass
print('PASS: five isolated package manifests, repeat-patch refusal, XML bounds, exact printable endpoint format')

with zipfile.ZipFile(frozen / 'games.wfs.anothereden.apk') as z:
    original_dex = z.read('classes5.dex')
patched_dex = patch_local_billing(original_dex)
assert len(patched_dex) == len(original_dex)
assert patched_dex[BILLING_SETUP_OFFSET:BILLING_SETUP_OFFSET + 2] == bytes.fromhex('280a')
assert patched_dex[BILLING_PURCHASES_OFFSET:BILLING_PURCHASES_OFFSET + 44] == bytes.fromhex(
    '2200a80912011a02a4157030062a100222016d02701055060100'
    '220294097040bf29120671107f2302000e00')
assert not any(patched_dex[BILLING_PURCHASES_OFFSET + 44:BILLING_PURCHASES_OFFSET + BILLING_PURCHASES_CODE_UNITS * 2])
assert patched_dex[BILLING_CATALOG_OFFSET:BILLING_CATALOG_OFFSET + 12] == bytes.fromhex('544080147220262250000e00')
assert not any(patched_dex[BILLING_CATALOG_OFFSET + 12:BILLING_CATALOG_OFFSET + BILLING_CATALOG_CODE_UNITS * 2])
assert patched_dex[BILLING_COUNTRY_OFFSET:BILLING_COUNTRY_OFFSET + 16] == bytes.fromhex(
    '5440ff101a018a687220262210000e00')
assert not any(patched_dex[BILLING_COUNTRY_OFFSET + 16:BILLING_COUNTRY_OFFSET + BILLING_COUNTRY_CODE_UNITS * 2])
assert patched_dex[BILLING_ORDER_CATALOG_OFFSET:BILLING_ORDER_CATALOG_OFFSET + 4] == bytes.fromhex('12110000')
assert patched_dex[BILLING_SUBMIT_OFFSET:BILLING_SUBMIT_OFFSET + 10] == bytes.fromhex('12007220262206000e00')
assert not any(patched_dex[BILLING_SUBMIT_OFFSET + 10:BILLING_SUBMIT_OFFSET + BILLING_SUBMIT_CODE_UNITS * 2])
assert patched_dex[BILLING_REQUEST_URL_OFFSET:BILLING_REQUEST_URL_OFFSET + 16] == bytes.fromhex(
    '7010460403001a0063515b30310d0e00')
assert not any(patched_dex[BILLING_REQUEST_URL_OFFSET + 16:BILLING_REQUEST_URL_OFFSET + BILLING_REQUEST_URL_CODE_UNITS * 2])
assert patched_dex[BILLING_SIGNED_RESPONSE_OFFSET:BILLING_SIGNED_RESPONSE_OFFSET + 2] == bytes.fromhex('1112')
assert patched_dex[BILLING_LOCAL_URL_STRING_OFFSET:BILLING_LOCAL_URL_STRING_OFFSET + 24] == (
    bytes([22]) + b'http://localhost:28765\0')
assert patched_dex[12:32] == hashlib.sha1(patched_dex[32:]).digest()
assert struct.unpack_from('<I', patched_dex, 8)[0] == zlib.adler32(patched_dex[12:]) & 0xffffffff
try:
    patch_local_billing(patched_dex)
    raise AssertionError('Double billing patch accepted')
except ValueError:
    pass
print('PASS: exact billing catalog adapter patch and DEX integrity fields')

header = (b'POST /us/private/game_client/user/login?secret=query HTTP/1.1\r\n'
          b'Host: 127.0.0.1:28765\r\nX-KMS-Token: secret-header\r\nContent-Length: 11\r\n\r\n')
metadata = request_metadata(header)
assert metadata['body_bytes'] == 11 and metadata['has_query']
assert metadata['route'] == '/us/private/game_client/user/login'
assert 'secret' not in json.dumps(metadata)
assert request_metadata(header.replace(b'user/login?secret=query', b'unknown-secret-path'))['route'] is None
for damaged in (header + b'x', header.replace(b'11\r\n', b'1048577\r\n'),
                header.replace(b'11\r\n', b'-1\r\n'), header.replace(b'11\r\n', b'11\r\nContent-Length: 11\r\n'),
                header.replace(b'11\r\n', b'11\r\nTransfer-Encoding: chunked\r\n'),
                header.replace(b'127.0.0.1:28765', b'example.com'), b'A'*32769,
                header.replace(b'POST ', b'CONNECT '), header.replace(b'X-KMS-Token:', b' Bad:')):
    try:
        request_metadata(damaged)
        raise AssertionError('Malformed framing accepted')
    except ValueError:
        pass


async def network_check():
    events = []
    async def handle(reader, writer):
        await respond(reader, writer, events.append, timeout=0.1)
    server = await asyncio.start_server(handle, '127.0.0.1', 0, limit=32768)
    async with server:
        for payload, code in ((header + b'secret-body', b'503'), (b'broken\r\n\r\n', b'400'),
                              (header, b'408'), (b'A'*32769 + b'\r\n\r\n', b'400')):
            reader, writer = await asyncio.open_connection('127.0.0.1', server.sockets[0].getsockname()[1])
            writer.write(payload)
            await writer.drain()
            response = await asyncio.wait_for(reader.read(), 2)
            assert response.startswith(b'HTTP/1.1 ' + code) and response.endswith(b'\r\n\r\n')
            assert b'Content-Length: 0' in response
            writer.close()
            await writer.wait_closed()
    assert [e['status'] for e in events] == [503, 400, 408, 400]
    assert 'secret' not in json.dumps(events)


asyncio.run(network_check())
print('PASS: local HTTP rejection, body/header bounds, malformed and ambiguous framing, timeout, no sensitive values in logs')

args = SimpleNamespace(command='install', adb='adb', serial='explicit-test-device')
with patch.object(probe, 'verify_probe', return_value=({}, Path('.'))), patch.object(client, 'adb') as adb:
    adb.side_effect = ['arm64-v8a', 'package:' + PACKAGE]
    try:
        probe.device(args)
        raise AssertionError('Existing private data was replaced')
    except ValueError as error:
        assert 'already installed' in str(error)
    assert all('install-multiple' not in call.args for call in adb.call_args_list)
print('PASS: existing private package installation refused without replacing app data')
