"""Small offline checks against the pinned local client; no Android mutation."""
import struct
import asyncio
import hashlib
import io
import json
import zipfile
import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import forevereden_client as client
import forevereden_probe as probe
from forevereden_probe import API_FORMAT, BILLING_CATALOG_CODE_UNITS, BILLING_CATALOG_OFFSET, BILLING_COUNTRY_CODE_UNITS, BILLING_COUNTRY_OFFSET, BILLING_LOCAL_URL_STRING_OFFSET, BILLING_ORDER_CATALOG_OFFSET, BILLING_PURCHASES_CODE_UNITS, BILLING_PURCHASES_OFFSET, BILLING_REQUEST_URL_CODE_UNITS, BILLING_REQUEST_URL_OFFSET, BILLING_SETUP_OFFSET, BILLING_SIGNED_RESPONSE_OFFSET, BILLING_SUBMIT_CODE_UNITS, BILLING_SUBMIT_OFFSET, COLLABO_FREEZE_END_AT, COLLABO_FREEZE_END_AT_BEFORE, COLLABO_FREEZE_END_AT_OFFSET, COLLABO_FREEZE_END_AT_PATCH, COLLABO_FREEZE_EXPIRED_END_AT_BEFORE, COLLABO_FREEZE_EXPIRED_END_AT_OFFSET, COLLABO_FREEZE_EXPIRED_END_AT_PATCH, ORIGINAL_URL, PACKAGE, chunks, patch_collabo_availability, patch_local_billing, patch_manifest, replace_fixed, request_metadata, respond

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

original_lib = None
for apk in client.APKS:
    with zipfile.ZipFile(frozen / apk) as z:
        if 'lib/arm64-v8a/libapp.so' in z.namelist():
            assert original_lib is None
            original_lib = z.read('lib/arm64-v8a/libapp.so')
assert original_lib is not None
story_lib = bytearray(original_lib)
identity_patch, story_skip = probe.patch_local_identity(story_lib)
assert story_lib[probe.SCRIPT_SKIP_EVENT_OFFSET:probe.SCRIPT_SKIP_EVENT_OFFSET + 4] == probe.arm64_branch(
    probe.SCRIPT_SKIP_EVENT_OFFSET, story_skip['script_skip_event_hook_address'])
assert story_lib[probe.MALLOC_PLT_OFFSET:probe.MALLOC_PLT_OFFSET + 4] == probe.arm64_branch(
    probe.MALLOC_PLT_OFFSET, story_skip['malloc_hook_address'])
assert story_lib[probe.REALLOC_PLT_OFFSET:probe.REALLOC_PLT_OFFSET + 4] == probe.arm64_branch(
    probe.REALLOC_PLT_OFFSET, story_skip['realloc_hook_address'])
assert story_lib[probe.CALLOC_PLT_OFFSET:probe.CALLOC_PLT_OFFSET + 4] == probe.arm64_branch(
    probe.CALLOC_PLT_OFFSET, story_skip['calloc_hook_address'])
assert story_lib[probe.POSIX_MEMALIGN_PLT_OFFSET:probe.POSIX_MEMALIGN_PLT_OFFSET + 4] == probe.arm64_branch(
    probe.POSIX_MEMALIGN_PLT_OFFSET, story_skip['posix_memalign_hook_address'])
assert story_skip['script_skip_event_hook_address'] > len(original_lib)
hook_file_offset = (identity_patch['segment_file_offset'] + story_skip['script_skip_event_hook_address']
                    - identity_patch['segment_virtual_address'])
hook_code = story_lib[hook_file_offset:hook_file_offset + 0x2c0]
assert hook_code.count(bytes.fromhex('60e20291')) == 3
cleanup_start = story_lib.index(b'local function S(f)pcall(f)end;')
cleanup = story_lib[cleanup_start:story_lib.index(b'\0', cleanup_start)]
for cleanup_call in (b'Custom_basicObjectRegist()', b'Custom_basicObjectSetVisible(true)',
                     b'Custom_basicObjectPlayAnim("idle",true)', b'Common_setFreeMovingEnable(true)',
                     b'Common_resetSpecificCharacterOnlyOnField()',
                     b'Common_forcePartyOverlapFadeIn()',
                     b'Common_stopVoice()', b'Common_stopNarration()', b'Common_closeCinemaTalk()',
                     b'Common_cancelSystemFadeIn()', b'Common_closeFadeUI()', b'Common_fadeIn(0)',
                     b'Common_hideTalkerForEvent(false)', b'Common_setLetterBox(false)',
                     b'Common_resetCameraInfo(0)', b'Common_setCameraState(Enum_CameraState.FIELD)',
                     b'pcall(Object_joinEvent,o,false)', b'pcall(Object_setInnerVisible,o,true)',
                     b'pcall(Object_setColor,o,1,1,1)', b'pcall(Object_setSpineAlpha,o,1)',
                     b'pcall(Object_setAlpha,o,1)', b'pcall(Object_setVisible,o,true)',
                     b'Enum_ObjectActionType.MOVE',
                     b'Enum_ObjectActionType.ROTATE', b'Enum_ObjectActionType.SCALE',
                     b'Enum_ObjectActionType.FADE'):
    assert cleanup_call in cleanup
assert cleanup.count(b'S(function()') >= 20
assert b'forevereden_prologue_skip\0' in story_lib
assert b'Common_areaChangeWithLine(511001003,1,0.690324664115906,false)' in story_lib
assert b'Common_clearScript()' not in story_lib[identity_patch['segment_file_offset']:
                                                identity_patch['segment_file_offset'] + identity_patch['segment_bytes']]
malloc_file_offset = (identity_patch['segment_file_offset'] + story_skip['malloc_hook_address']
                      - identity_patch['segment_virtual_address'])
malloc_code = story_lib[malloc_file_offset:malloc_file_offset + 52]
assert malloc_code[:4] == bytes.fromhex('1f0001f1')
assert malloc_code[8:12] == bytes.fromhex('1f4001f1')
assert malloc_code[40:48] == bytes.fromhex('000c80d2') + probe.arm64_adrp(
    16, story_skip['malloc_hook_address'] + 44, probe.MALLOC_GOT_OFFSET)
realloc_file_offset = (identity_patch['segment_file_offset'] + story_skip['realloc_hook_address']
                       - identity_patch['segment_virtual_address'])
realloc_code = story_lib[realloc_file_offset:realloc_file_offset + 52]
assert realloc_code[:4] == bytes.fromhex('3f0001f1')
assert realloc_code[8:12] == bytes.fromhex('3f4001f1')
assert realloc_code[40:48] == bytes.fromhex('010c80d2') + probe.arm64_adrp(
    16, story_skip['realloc_hook_address'] + 44, probe.REALLOC_GOT_OFFSET)
calloc_file_offset = (identity_patch['segment_file_offset'] + story_skip['calloc_hook_address']
                      - identity_patch['segment_virtual_address'])
calloc_code = story_lib[calloc_file_offset:calloc_file_offset + 60]
assert calloc_code[:8] == bytes.fromhex('027c019b3f0001f1')
assert calloc_code[12:16] == bytes.fromhex('5f4001f1')
assert calloc_code[44:56] == bytes.fromhex('000c80d2210080d2') + probe.arm64_adrp(
    16, story_skip['calloc_hook_address'] + 52, probe.CALLOC_GOT_OFFSET)
posix_file_offset = (identity_patch['segment_file_offset'] + story_skip['posix_memalign_hook_address']
                     - identity_patch['segment_virtual_address'])
posix_code = story_lib[posix_file_offset:posix_file_offset + 52]
assert posix_code[:4] == bytes.fromhex('5f0001f1')
assert posix_code[8:12] == bytes.fromhex('5f4001f1')
assert posix_code[40:48] == bytes.fromhex('020c80d2') + probe.arm64_adrp(
    16, story_skip['posix_memalign_hook_address'] + 44, probe.POSIX_MEMALIGN_GOT_OFFSET)
assert story_skip['allocation_counter_address'] == identity_patch['segment_virtual_address'] - 8
elf = struct.unpack_from('<16sHHIQQQIHHHHHH', story_lib)
programs = [struct.unpack_from('<IIQQQQQQ', story_lib, elf[5] + i * elf[9]) for i in range(elf[10])]
assert any(p[0] == 1 and p[1] == 5 and p[3] == identity_patch['segment_virtual_address'] for p in programs)
assert any(p[0] == 1 and p[1] == 6 and p[3] < story_skip['allocation_counter_address']
           and p[3] + p[6] == identity_patch['segment_virtual_address'] for p in programs)
assert story_skip['prologue_skip_destination'] == {
    'area_id': 511001003, 'line_id': 1, 'rate': 0.690324664115906,
    'story_step': 'story_step.story_step_ch1_1'}
assert all(value in story_skip['behavior'] for value in ('independently clear voice', 'narration',
                                                          'every fade layer', 'letterbox',
                                                          'actor actions', 'party registration',
                                                          'alpha', 'visibility filters', 'idle animation',
                                                          'field movement', 'final cleanup'))
try:
    probe.patch_local_identity(story_lib)
    raise AssertionError('Double story-skip patch accepted')
except ValueError:
    pass
print('PASS: TalkSkip cleanup and pinned 96-byte Scudo allocation-class split')

with zipfile.ZipFile(frozen / 'AssetPack1.apk') as z:
    original_lua_zip = z.read('assets/lua.zip')
patched_lua_zip, opening_lua = probe.patch_opening_lua(original_lua_zip)
with zipfile.ZipFile(io.BytesIO(original_lua_zip)) as original, zipfile.ZipFile(io.BytesIO(patched_lua_zip)) as patched:
    assert original.namelist() == patched.namelist()
    assert all(original.read(name) == patched.read(name) for name in original.namelist()
               if name not in probe.OPENING_LUA_MEMBERS)
    assert all(original.read(name) != patched.read(name) for name in probe.OPENING_LUA_MEMBERS)
assert {item['member'] for item in opening_lua['members']} == probe.OPENING_LUA_MEMBERS
behaviors = ' '.join(item['behavior'] for item in opening_lua['members'])
assert 'register and show' in behaviors and 'forest-to-house area transition' in behaviors
assert any(item[0] == 'story/episode1/event.prologue1.enc' and b'Sequence_waitAreaChange()' in item[5]
           and b'skipEvent=FE_skip_update' in item[5] for item in probe.OPENING_LUA_PATCHES)
try:
    probe.patch_opening_lua(patched_lua_zip)
    raise AssertionError('Double opening Lua patch accepted')
except ValueError:
    pass
print('PASS: opening Lua keeps party visibility and waits for the forest-to-house transition; no other member changes')

patched_lib = bytearray(original_lib)
metadata = patch_collabo_availability(patched_lib)
assert len(patched_lib) == len(original_lib)
assert original_lib[COLLABO_FREEZE_END_AT_OFFSET:COLLABO_FREEZE_END_AT_OFFSET + 16] == COLLABO_FREEZE_END_AT_BEFORE
assert patched_lib[COLLABO_FREEZE_END_AT_OFFSET:COLLABO_FREEZE_END_AT_OFFSET + 16] == COLLABO_FREEZE_END_AT_PATCH
assert original_lib[COLLABO_FREEZE_EXPIRED_END_AT_OFFSET:COLLABO_FREEZE_EXPIRED_END_AT_OFFSET + 16] == COLLABO_FREEZE_EXPIRED_END_AT_BEFORE
assert patched_lib[COLLABO_FREEZE_EXPIRED_END_AT_OFFSET:COLLABO_FREEZE_EXPIRED_END_AT_OFFSET + 16] == COLLABO_FREEZE_EXPIRED_END_AT_PATCH
assert metadata['end_at'] == COLLABO_FREEZE_END_AT and metadata['extension_years'] == 9999
try:
    patch_collabo_availability(patched_lib)
    raise AssertionError('Double collaboration patch accepted')
except ValueError:
    pass
print('PASS: shared collaboration cutoff and expiration predicate extended by 9,999 years with exact-byte guards')

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
