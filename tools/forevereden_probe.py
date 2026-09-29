"""Build a separate, local-only routing probe from the pinned Android APKs.

This is not a game server. Its listener rejects requests with HTTP 503 and
records only route/header names and lengths, never tokens or request bodies.
"""
import argparse
import asyncio
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import struct
import subprocess
import sys
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
TALK_LAYER_ADDED_OFFSET = 0x2FD1DFC
TALK_LAYER_ADDED_BEFORE = bytes.fromhex('e00313aa')
TALK_LAYER_ADDED_CONTINUE_OFFSET = 0x2FD1E00
TALK_FINISH_OFFSET = 0x2FD0434
TALK_FINISH_BEFORE = bytes.fromhex('fd7bbea9')
TALK_SKIP_MANAGER_OFFSET = 0x336E1C8
TALK_SKIP_STATE_GET_OFFSET = 0x336F31C
TALK_SKIP_STATE_REMOVE_OFFSET = 0x336EE4C
TALK_SKIP_CREATE_CONTINUE_OFFSET = 0x31E7800
TALK_SKIP_INIT_FLAG_OFFSET = 0x31E78C4
TALK_SKIP_INIT_FLAG_BEFORE = bytes.fromhex('21008052')
TALK_SKIP_INIT_FLAG_PATCH = bytes.fromhex('01008052')
SCRIPT_SKIP_EVENT_OFFSET = 0x31DF458
SCRIPT_SKIP_EVENT_BEFORE = bytes.fromhex('fd7bbea9')
SCRIPT_FUNCTION_FIND_OFFSET = 0x31DFFB8
SCRIPT_UPDATE_NAME_ADDRESS = 0x48C3D60
SCRIPT_FINAL_NAME_ADDRESS = 0x48C3D90
SCRIPT_SKIP_EVENT_NAME_ADDRESS = 0x48C3DC0
MALLOC_PLT_OFFSET = 0x42C0F00
MALLOC_PLT_BEFORE = bytes.fromhex('d02e00d0')
MALLOC_GOT_OFFSET = 0x489A9D0
REALLOC_PLT_OFFSET = 0x42C1840
REALLOC_PLT_BEFORE = bytes.fromhex('d02e00b0')
REALLOC_GOT_OFFSET = 0x489AE70
CALLOC_PLT_OFFSET = 0x42C1E50
CALLOC_PLT_BEFORE = bytes.fromhex('d02e00d0')
CALLOC_GOT_OFFSET = 0x489B178
POSIX_MEMALIGN_PLT_OFFSET = 0x42D59A0
POSIX_MEMALIGN_PLT_BEFORE = bytes.fromhex('702e00f0')
POSIX_MEMALIGN_GOT_OFFSET = 0x48A4F20
LUA_TYPE_OFFSET = 0x3CAF6D0
LUA_GETFIELD_OFFSET = 0x3CB0D70
LUA_PUSHBOOLEAN_OFFSET = 0x3CB0880
LUA_PCALL_OFFSET = 0x3CB1938
LUA_SETTOP_OFFSET = 0x3CAF3C4
LUA_TOBOOLEAN_OFFSET = 0x3CAFF70
LUAL_LOADBUFFER_OFFSET = 0x3CBA4E8
COLLABO_FREEZE_END_AT_OFFSET = 0x35AE208
COLLABO_FREEZE_END_AT_BEFORE = bytes.fromhex('006040f981018052e2031faa6f22b117')
COLLABO_FREEZE_EXPIRED_END_AT_OFFSET = 0x35AB21C
COLLABO_FREEZE_EXPIRED_END_AT_BEFORE = bytes.fromhex('606240f981018052e2031faa6a2eb197')
COLLABO_FREEZE_END_AT = 317321333999  # 12025-07-06 14:59:59 UTC; original cutoff + 9,999 years.
COLLABO_FREEZE_END_AT_PATCH = bytes.fromhex('e09d89d2603abcf22009c0f2c0035fd6')
COLLABO_FREEZE_EXPIRED_END_AT_PATCH = bytes.fromhex('e09d89d2603abcf22009c0f21f2003d5')
LUA_ZIP_BYTES = 113325756
LUA_ZIP_SHA256 = 'f026c13545cebcdada2b98b57553e837c87e00726c2aad46c48d093aeb501e04'
OPENING_LUA_PATCHES = (
    ('area/area_511001003/area_511001003.enc',
     '2dbfd85cb86608b0406b193bb3e6e9652b94a5fdd44f7503c53f9fb8df8dfbce',
     '96f8e66f5698da2ece7a38492535b312fb3da3912f2762d83fe972759f48cd44', b'\x03' * 3,
     b'local function j(By21Im)\nif Common_isStoryStepActive',
     (b'local function j(By21Im)\n'
      b'if Common_isStoryStepComplete(story_step_story_step_ch1_1)then '
      b'Custom_basicObjectRegist()Custom_basicObjectSetVisible(true)end;'
      b'if Common_isStoryStepActive'),
     'register and show the basic party object on house entry after the opening step completes'),
    ('story/episode1/event.prologue1.enc',
     'a921cb48081b1f9b0a4db128c3f03d5bb4d0e03685eebefea301f3f31d58dafd',
     '3ce1ae8fdf030b188f909b00252238972f21f9e0d364e9f7b5c61b271161bcd0', b'\x02' * 2,
     (b'local function By21Im(WsNl3)\n'
      b'Common_fireStoryStepTrigger(story_step_story_step_ch1_1)Common_setSystemFlag(system_flag_feature_notice,1)end\n'
      b'Common_registLocalFunction({regist=yNaJIpm9,activate=j,init=tTiOG8,update=m6WFkQ7,final=By21Im})'),
     (b'local FE_skip_steps={Sequence_stopAllSE(),Sequence_fadeOut(0),Sequence_waitFade(),'
      b'Sequence_clearScript(),Sequence_areaChange(511001003,2,false),Sequence_waitAreaChange(),'
      b'Sequence_invoke(function()Common_stopVoice()Common_deleteTalkSkipButton()'
      b'Custom_basicObjectRegist()Custom_basicObjectSetVisible(true)'
      b'Common_resetPartyPosition(511001003,2,Enum_ObjectDirection.NONE,'
      b'{resetCamera=true,offsetX=-209,offsetY=0,offsetZ=0})Common_resetCameraInfo(0)end),'
      b'Sequence_fadeIn(0),Sequence_waitFade()}\n'
      b'local FE_skip=Sequence_create("skipEvent",FE_skip_steps)\n'
      b'local function FE_skip_update(o)if FE_skip:exec(o)==Enum_SequenceState.FINISH then return true end;return false end\n'
      b'local function By21Im(WsNl3)\n'
      b'Common_fireStoryStepTrigger(story_step_story_step_ch1_1)Common_setSystemFlag(system_flag_feature_notice,1)end\n'
      b'Common_registLocalFunction({regist=yNaJIpm9,activate=j,init=tTiOG8,update=m6WFkQ7,final=By21Im,skipEvent=FE_skip_update})'),
     'run the authored forest-to-house area transition to completion before committing opening story state'),
)
OPENING_LUA_MEMBERS = frozenset(patch[0] for patch in OPENING_LUA_PATCHES)
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


def arm64_call(pc, target):
    instruction, = struct.unpack('<I', arm64_branch(pc, target))
    return struct.pack('<I', instruction | 0x80000000)


def arm64_cbnz_x(register, pc, target):
    distance = target - pc
    if not 0 <= register < 32 or distance % 4 or not -(1 << 20) <= distance < (1 << 20):
        raise ValueError('ARM64 CBNZ target is out of range')
    return struct.pack('<I', 0xb5000000 | (((distance >> 2) & 0x7ffff) << 5) | register)


def arm64_b_cond(pc, target, condition):
    distance = target - pc
    if not 0 <= condition < 16 or distance % 4 or not -(1 << 20) <= distance < (1 << 20):
        raise ValueError('ARM64 conditional branch target is out of range')
    return struct.pack('<I', 0x54000000 | (((distance >> 2) & 0x7ffff) << 5) | condition)


def arm64_tbnz_w(register, bit, pc, target):
    distance = target - pc
    if not 0 <= register < 32 or not 0 <= bit < 32 or distance % 4 or not -(1 << 15) <= distance < (1 << 15):
        raise ValueError('ARM64 TBNZ target is out of range')
    return struct.pack('<I', 0x37000000 | (bit << 19) | (((distance >> 2) & 0x3fff) << 5) | register)


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
            loads.append((index, values))
        elif values[0] == 4 and values[2:7] == (0x238, 0x238, 0x238, 0xbc, 0xbc):
            note = index
    if len(loads) != 3 or note is None:
        raise ValueError('Pinned libapp program headers changed')
    file_offset = (len(data) + ELF_PAGE - 1) & -ELF_PAGE
    writable_index, writable = max(loads, key=lambda item: item[1][3] + item[1][6])
    if writable[1] != 6:
        raise ValueError('Pinned writable libapp segment changed')
    virtual_address = (writable[3] + writable[6] + ELF_PAGE - 1) & -ELF_PAGE
    object_address = virtual_address + 0x100
    payload = bytearray(ELF_PAGE)
    payload[:4] = arm64_adrp(1, virtual_address, object_address)
    payload[4:8] = struct.pack('<I', 0x91000021 | ((object_address & 0xfff) << 10))
    payload[8:12] = bytes.fromhex('e00308aa')
    payload[12:16] = arm64_branch(virtual_address + 12, STRING_COPY_OFFSET)
    encoded = LOCAL_USER_ID.encode()
    payload[0x100:0x118] = bytes([len(encoded) * 2]) + encoded + b'\0' * (23 - len(encoded))
    hook = virtual_address + 0x200
    create = virtual_address + 0x240
    finish_hook = virtual_address + 0x300
    skip_event_hook = virtual_address + 0x380
    skip_cleanup_name = virtual_address + 0xa00
    skip_cleanup_source = virtual_address + 0xa40
    malloc_hook = virtual_address + 0x640
    realloc_hook = virtual_address + 0x680
    calloc_hook = virtual_address + 0x6c0
    posix_memalign_hook = virtual_address + 0x700
    allocation_counter = virtual_address - 8
    prologue_skip_name = virtual_address + 0x780
    prologue_skip_source = virtual_address + 0x800
    prologue_skip = (
        b'if Common_isStoryStepActive(story_step_story_step_ch1_1) then '
        b'Custom_basicObjectSetVisible(true);Common_resetCameraInfo(0);'
        b'Common_deleteTalkSkipButton();'
        b'Common_areaChangeWithLine(511001003,1,0.690324664115906,false);'
        b'return true end return false')
    generic_cleanup = (
        b'local function S(f)pcall(f)end;'
        b'S(function()Custom_basicObjectRegist()end);'
        b'local O={CBO_PARTY1,CBO_PARTY2,CBO_PARTY3,CBO_PARTY4,CBO_PET};'
        b'for _,o in ipairs(O)do S(function()if Object_exists(o)then '
        b'pcall(Object_removeAction,o,Enum_ObjectActionType.MOVE);'
        b'pcall(Object_removeAction,o,Enum_ObjectActionType.ROTATE);'
        b'pcall(Object_removeAction,o,Enum_ObjectActionType.SCALE);'
        b'pcall(Object_removeAction,o,Enum_ObjectActionType.FADE);'
        b'pcall(Object_joinEvent,o,false);pcall(Object_setInnerVisible,o,true);'
        b'pcall(Object_setColor,o,1,1,1);pcall(Object_setSpineAlpha,o,1);'
        b'pcall(Object_setAlpha,o,1);pcall(Object_setVisible,o,true)end end)end;'
        b'S(function()Object_removeAction(CBO_CAMERA,Enum_ObjectActionType.MOVE)end);'
        b'S(function()Object_removeAction(CBO_CAMERA,Enum_ObjectActionType.ROTATE)end);'
        b'S(function()Object_removeAction(CBO_CAMERA,Enum_ObjectActionType.SCALE)end);'
        b'S(function()Custom_basicObjectSetVisible(true)end);'
        b'S(function()Custom_basicObjectPlayAnim("idle",true)end);'
        b'S(function()Common_resetSpecificCharacterOnlyOnField()end);'
        b'S(function()Common_forcePartyOverlapFadeIn()end);'
        b'S(function()Common_setFreeMovingEnable(true)end);'
        b'S(function()Common_stopVoice()end);S(function()Common_stopNarration()end);'
        b'S(function()Common_deleteTalkSkipButton()end);'
        b'S(function()Common_closeCinemaTalk()end);'
        b'S(function()Common_cancelSystemFadeIn()end);S(function()Common_closeFadeUI()end);'
        b'S(function()Common_fadeIn(0)end);S(function()Common_hideTalkerForEvent(false)end);'
        b'S(function()Common_setLetterBox(false)end);S(function()Common_resetCameraInfo(0)end);'
        b'S(function()Common_setCameraState(Enum_CameraState.FIELD)end);'
        b'S(function()Custom_basicObjectSetVisible(true)end)')
    payload[skip_cleanup_name - virtual_address:skip_cleanup_name - virtual_address + 25] = b'forevereden_skip_cleanup\0'
    payload[skip_cleanup_source - virtual_address:skip_cleanup_source - virtual_address + len(generic_cleanup)] = generic_cleanup
    payload[prologue_skip_name - virtual_address:prologue_skip_name - virtual_address + 25] = b'forevereden_prologue_skip\0'
    payload[prologue_skip_source - virtual_address:prologue_skip_source - virtual_address + len(prologue_skip)] = prologue_skip
    def split_saturated_class(code, hook_address, replacement):
        code += arm64_adrp(9, hook_address + len(code), allocation_counter)
        code += struct.pack('<I', 0x91000000 | ((allocation_counter & 0xfff) << 10) | (9 << 5) | 9)
        code += bytes.fromhex('2a0140394b0500112b010039')  # load, increment, and store the shared byte counter
        keep_original = len(code)
        code += b'\0' * 4
        code += replacement
        original = hook_address + len(code)
        code[keep_original:keep_original + 4] = arm64_tbnz_w(
            10, 0, hook_address + keep_original, original)
        return original

    code = bytearray(bytes.fromhex('1f0001f1'))  # cmp x0, #64
    low_or_equal = len(code)
    code += b'\0' * 4
    code += bytes.fromhex('1f4001f1')  # cmp x0, #80
    high = len(code)
    code += b'\0' * 4
    original_malloc = split_saturated_class(code, malloc_hook, bytes.fromhex('000c80d2'))
    code[low_or_equal:low_or_equal + 4] = arm64_b_cond(
        malloc_hook + low_or_equal, original_malloc, 9)
    code[high:high + 4] = arm64_b_cond(malloc_hook + high, original_malloc, 8)
    code += arm64_adrp(16, original_malloc, MALLOC_GOT_OFFSET)
    code += arm64_branch(malloc_hook + len(code), MALLOC_PLT_OFFSET + 4)
    payload[malloc_hook - virtual_address:malloc_hook - virtual_address + len(code)] = code
    code = bytearray(bytes.fromhex('3f0001f1'))  # cmp x1, #64
    low_or_equal = len(code)
    code += b'\0' * 4
    code += bytes.fromhex('3f4001f1')  # cmp x1, #80
    high = len(code)
    code += b'\0' * 4
    original_realloc = split_saturated_class(code, realloc_hook, bytes.fromhex('010c80d2'))
    code[low_or_equal:low_or_equal + 4] = arm64_b_cond(
        realloc_hook + low_or_equal, original_realloc, 9)
    code[high:high + 4] = arm64_b_cond(realloc_hook + high, original_realloc, 8)
    code += arm64_adrp(16, original_realloc, REALLOC_GOT_OFFSET)
    code += arm64_branch(realloc_hook + len(code), REALLOC_PLT_OFFSET + 4)
    payload[realloc_hook - virtual_address:realloc_hook - virtual_address + len(code)] = code
    code = bytearray(bytes.fromhex('027c019b3f0001f1'))  # mul x2, x0, x1; cmp x2, #64
    low_or_equal = len(code)
    code += b'\0' * 4
    code += bytes.fromhex('5f4001f1')  # cmp x2, #80
    high = len(code)
    code += b'\0' * 4
    original_calloc = split_saturated_class(
        code, calloc_hook, bytes.fromhex('000c80d2210080d2'))  # calloc(96, 1)
    code[low_or_equal:low_or_equal + 4] = arm64_b_cond(
        calloc_hook + low_or_equal, original_calloc, 9)
    code[high:high + 4] = arm64_b_cond(calloc_hook + high, original_calloc, 8)
    code += arm64_adrp(16, original_calloc, CALLOC_GOT_OFFSET)
    code += arm64_branch(calloc_hook + len(code), CALLOC_PLT_OFFSET + 4)
    payload[calloc_hook - virtual_address:calloc_hook - virtual_address + len(code)] = code
    code = bytearray(bytes.fromhex('5f0001f1'))  # cmp x2, #64
    low_or_equal = len(code)
    code += b'\0' * 4
    code += bytes.fromhex('5f4001f1')  # cmp x2, #80
    high = len(code)
    code += b'\0' * 4
    original_posix_memalign = split_saturated_class(
        code, posix_memalign_hook, bytes.fromhex('020c80d2'))
    code[low_or_equal:low_or_equal + 4] = arm64_b_cond(
        posix_memalign_hook + low_or_equal, original_posix_memalign, 9)
    code[high:high + 4] = arm64_b_cond(posix_memalign_hook + high, original_posix_memalign, 8)
    code += arm64_adrp(16, original_posix_memalign, POSIX_MEMALIGN_GOT_OFFSET)
    code += arm64_branch(posix_memalign_hook + len(code), POSIX_MEMALIGN_PLT_OFFSET + 4)
    payload[posix_memalign_hook - virtual_address:posix_memalign_hook - virtual_address + len(code)] = code
    finish = hook + 20
    payload[0x200:0x204] = arm64_call(hook, TALK_SKIP_MANAGER_OFFSET)
    payload[0x204:0x208] = bytes.fromhex('61328052')  # mov w1, #0x193
    payload[0x208:0x20c] = arm64_call(hook + 8, TALK_SKIP_STATE_GET_OFFSET)
    payload[0x20c:0x210] = arm64_cbnz_x(0, hook + 12, finish)
    payload[0x210:0x214] = arm64_call(hook + 16, create)
    payload[0x214:0x218] = TALK_LAYER_ADDED_BEFORE
    payload[0x218:0x21c] = arm64_branch(hook + 24, TALK_LAYER_ADDED_CONTINUE_OFFSET)
    create_code = bytes.fromhex(
        'ffc302d1fd7b07a9f74300f9f65709a9f44f0aa9fdc30191'
        '56d03bd5c81640f9a8831ff834008052')
    payload[0x240:0x240 + len(create_code)] = create_code
    create_call = create + len(create_code)
    payload[0x240 + len(create_code):0x244 + len(create_code)] = arm64_call(create_call, TALK_SKIP_MANAGER_OFFSET)
    create_branch = create_call + 4
    payload[0x244 + len(create_code):0x248 + len(create_code)] = arm64_branch(create_branch, TALK_SKIP_CREATE_CONTINUE_OFFSET)
    code = bytearray.fromhex('ff8300d1f37b01a9e00300f9')
    code += arm64_call(finish_hook + len(code), TALK_SKIP_MANAGER_OFFSET)
    code += bytes.fromhex('61328052')  # mov w1, #0x193
    code += arm64_call(finish_hook + len(code), TALK_SKIP_STATE_GET_OFFSET)
    code += arm64_cbnz_x(0, finish_hook + len(code), finish_hook + 32)
    code += arm64_branch(finish_hook + len(code), finish_hook + 48)
    code += bytes.fromhex('f30300aa')  # mov x19, x0
    code += arm64_call(finish_hook + len(code), TALK_SKIP_MANAGER_OFFSET)
    code += bytes.fromhex('e10313aa')  # mov x1, x19
    code += arm64_call(finish_hook + len(code), TALK_SKIP_STATE_REMOVE_OFFSET)
    code += bytes.fromhex('e00340f9f37b41a9ff830091')
    code += TALK_FINISH_BEFORE
    code += arm64_branch(finish_hook + len(code), TALK_FINISH_OFFSET + 4)
    payload[finish_hook - virtual_address:finish_hook - virtual_address + len(code)] = code
    code = bytearray.fromhex('fd7bbea9f30b00f9fd030091f30300aa')
    code += arm64_adrp(1, skip_event_hook + len(code), SCRIPT_SKIP_EVENT_NAME_ADDRESS)
    code += struct.pack('<I', 0x91000021 | ((SCRIPT_SKIP_EVENT_NAME_ADDRESS & 0xfff) << 10))
    code += bytes.fromhex('60e20291')  # add x0, x19, #0xb8
    code += arm64_call(skip_event_hook + len(code), SCRIPT_FUNCTION_FIND_OFFSET)
    code += bytes.fromhex('680203911f0100eb')  # map end; cmp end, result
    missing_skip_branch = len(code)
    code += b'\0' * 4
    code += bytes.fromhex('2800805268e20839')  # pending skipEvent = true
    native_return_branch = len(code)
    code += b'\0' * 4
    missing_skip = skip_event_hook + len(code)
    code[missing_skip_branch:missing_skip_branch + 4] = arm64_b_cond(
        skip_event_hook + missing_skip_branch, missing_skip, 0)
    code += bytes.fromhex('601e40f9')  # Lua state
    code += arm64_adrp(1, skip_event_hook + len(code), prologue_skip_source)
    code += struct.pack('<I', 0x91000021 | ((prologue_skip_source & 0xfff) << 10))
    code += struct.pack('<I', 0xd2800002 | (len(prologue_skip) << 5))
    code += arm64_adrp(3, skip_event_hook + len(code), prologue_skip_name)
    code += struct.pack('<I', 0x91000063 | ((prologue_skip_name & 0xfff) << 10))
    code += arm64_call(skip_event_hook + len(code), LUAL_LOADBUFFER_OFFSET)
    load_error_branch = len(code)
    code += b'\0' * 4
    code += bytes.fromhex('601e40f9010080522200805203008052')  # state; pcall(0, 1, 0)
    code += arm64_call(skip_event_hook + len(code), LUA_PCALL_OFFSET)
    call_error_branch = len(code)
    code += b'\0' * 4
    code += bytes.fromhex('601e40f901008012')  # state; stack index -1
    code += arm64_call(skip_event_hook + len(code), LUA_TOBOOLEAN_OFFSET)
    prologue_handled_branch = len(code)
    code += b'\0' * 4
    code += bytes.fromhex('601e40f921008012')  # pop false result
    code += arm64_call(skip_event_hook + len(code), LUA_SETTOP_OFFSET)
    generic_fallback_branch = len(code)
    code += b'\0' * 4
    prologue_error = skip_event_hook + len(code)
    code[load_error_branch:load_error_branch + 4] = arm64_cbnz_x(
        0, skip_event_hook + load_error_branch, prologue_error)
    code[call_error_branch:call_error_branch + 4] = arm64_cbnz_x(
        0, skip_event_hook + call_error_branch, prologue_error)
    code += bytes.fromhex('601e40f921008012')  # pop Lua error
    code += arm64_call(skip_event_hook + len(code), LUA_SETTOP_OFFSET)
    error_fallback_branch = len(code)
    code += b'\0' * 4
    prologue_handled = skip_event_hook + len(code)
    code[prologue_handled_branch:prologue_handled_branch + 4] = arm64_cbnz_x(
        0, skip_event_hook + prologue_handled_branch, prologue_handled)
    code += bytes.fromhex('601e40f921008012')  # pop true result
    code += arm64_call(skip_event_hook + len(code), LUA_SETTOP_OFFSET)
    prologue_return_branch = len(code)
    code += b'\0' * 4
    generic_fallback = skip_event_hook + len(code)
    code[generic_fallback_branch:generic_fallback_branch + 4] = arm64_branch(
        skip_event_hook + generic_fallback_branch, generic_fallback)
    code[error_fallback_branch:error_fallback_branch + 4] = arm64_branch(
        skip_event_hook + error_fallback_branch, generic_fallback)
    code += bytes.fromhex('601e40f9')  # Lua state
    code += arm64_adrp(1, skip_event_hook + len(code), skip_cleanup_source)
    code += struct.pack('<I', 0x91000021 | ((skip_cleanup_source & 0xfff) << 10))
    code += struct.pack('<I', 0xd2800002 | (len(generic_cleanup) << 5))
    code += arm64_adrp(3, skip_event_hook + len(code), skip_cleanup_name)
    code += struct.pack('<I', 0x91000063 | ((skip_cleanup_name & 0xfff) << 10))
    code += arm64_call(skip_event_hook + len(code), LUAL_LOADBUFFER_OFFSET)
    cleanup_load_error = len(code)
    code += b'\0' * 4
    code += bytes.fromhex('601e40f9010080520200805203008052')  # state; pcall(0, 0, 0)
    code += arm64_call(skip_event_hook + len(code), LUA_PCALL_OFFSET)
    cleanup_call_error = len(code)
    code += b'\0' * 4
    cleanup_done_branch = len(code)
    code += b'\0' * 4
    cleanup_error = skip_event_hook + len(code)
    code[cleanup_load_error:cleanup_load_error + 4] = arm64_cbnz_x(
        0, skip_event_hook + cleanup_load_error, cleanup_error)
    code[cleanup_call_error:cleanup_call_error + 4] = arm64_cbnz_x(
        0, skip_event_hook + cleanup_call_error, cleanup_error)
    code += bytes.fromhex('601e40f921008012')  # Lua state; pop error
    code += arm64_call(skip_event_hook + len(code), LUA_SETTOP_OFFSET)
    cleanup_done = skip_event_hook + len(code)
    code[cleanup_done_branch:cleanup_done_branch + 4] = arm64_branch(
        skip_event_hook + cleanup_done_branch, cleanup_done)
    code += arm64_adrp(1, skip_event_hook + len(code), SCRIPT_UPDATE_NAME_ADDRESS)
    code += struct.pack('<I', 0x91000021 | ((SCRIPT_UPDATE_NAME_ADDRESS & 0xfff) << 10))
    code += bytes.fromhex('60e20291')
    code += arm64_call(skip_event_hook + len(code), SCRIPT_FUNCTION_FIND_OFFSET)
    code += bytes.fromhex('680203911f0100eb')
    missing_update_branch = len(code)
    code += b'\0' * 4
    code += bytes.fromhex('1fe00039')  # active update = false
    activate_final = skip_event_hook + len(code)
    code[missing_update_branch:missing_update_branch + 4] = arm64_b_cond(
        skip_event_hook + missing_update_branch, activate_final, 0)
    code += arm64_adrp(1, skip_event_hook + len(code), SCRIPT_FINAL_NAME_ADDRESS)
    code += struct.pack('<I', 0x91000021 | ((SCRIPT_FINAL_NAME_ADDRESS & 0xfff) << 10))
    code += bytes.fromhex('60e20291')
    code += arm64_call(skip_event_hook + len(code), SCRIPT_FUNCTION_FIND_OFFSET)
    code += bytes.fromhex('680203911f0100eb')
    missing_final_branch = len(code)
    code += b'\0' * 4
    code += bytes.fromhex('2800805208e00039')  # active final = true
    return_from_skip = skip_event_hook + len(code)
    code[prologue_return_branch:prologue_return_branch + 4] = arm64_branch(
        skip_event_hook + prologue_return_branch, generic_fallback)
    code[native_return_branch:native_return_branch + 4] = arm64_branch(
        skip_event_hook + native_return_branch, return_from_skip)
    code[missing_final_branch:missing_final_branch + 4] = arm64_b_cond(
        skip_event_hook + missing_final_branch, return_from_skip, 0)
    code += bytes.fromhex('f30b40f9fd7bc2a8c0035fd6')
    if len(code) > malloc_hook - skip_event_hook:
        raise ValueError('Story-skip hook exceeds its pinned code cave')
    payload[skip_event_hook - virtual_address:skip_event_hook - virtual_address + len(code)] = code
    if data[TALK_LAYER_ADDED_OFFSET:TALK_LAYER_ADDED_OFFSET + 4] != TALK_LAYER_ADDED_BEFORE:
        raise ValueError('Pinned TalkLayer scene-add continuation changed')
    if data[TALK_FINISH_OFFSET:TALK_FINISH_OFFSET + 4] != TALK_FINISH_BEFORE:
        raise ValueError('Pinned talk-finish cleanup changed')
    if data[TALK_SKIP_INIT_FLAG_OFFSET:TALK_SKIP_INIT_FLAG_OFFSET + 4] != TALK_SKIP_INIT_FLAG_BEFORE:
        raise ValueError('Pinned TalkSkip initialization changed')
    if data[SCRIPT_SKIP_EVENT_OFFSET:SCRIPT_SKIP_EVENT_OFFSET + 4] != SCRIPT_SKIP_EVENT_BEFORE:
        raise ValueError('Pinned Script::skipEvent changed')
    if data[MALLOC_PLT_OFFSET:MALLOC_PLT_OFFSET + 4] != MALLOC_PLT_BEFORE:
        raise ValueError('Pinned malloc PLT entry changed')
    if data[REALLOC_PLT_OFFSET:REALLOC_PLT_OFFSET + 4] != REALLOC_PLT_BEFORE:
        raise ValueError('Pinned realloc PLT entry changed')
    if data[CALLOC_PLT_OFFSET:CALLOC_PLT_OFFSET + 4] != CALLOC_PLT_BEFORE:
        raise ValueError('Pinned calloc PLT entry changed')
    if data[POSIX_MEMALIGN_PLT_OFFSET:POSIX_MEMALIGN_PLT_OFFSET + 4] != POSIX_MEMALIGN_PLT_BEFORE:
        raise ValueError('Pinned posix_memalign PLT entry changed')
    data[XUID_GETTER_OFFSET:XUID_GETTER_OFFSET + 4] = arm64_branch(XUID_GETTER_OFFSET, virtual_address)
    data[TALK_LAYER_ADDED_OFFSET:TALK_LAYER_ADDED_OFFSET + 4] = arm64_branch(TALK_LAYER_ADDED_OFFSET, hook)
    data[TALK_FINISH_OFFSET:TALK_FINISH_OFFSET + 4] = arm64_branch(TALK_FINISH_OFFSET, finish_hook)
    data[TALK_SKIP_INIT_FLAG_OFFSET:TALK_SKIP_INIT_FLAG_OFFSET + 4] = TALK_SKIP_INIT_FLAG_PATCH
    data[SCRIPT_SKIP_EVENT_OFFSET:SCRIPT_SKIP_EVENT_OFFSET + 4] = arm64_branch(
        SCRIPT_SKIP_EVENT_OFFSET, skip_event_hook)
    data[MALLOC_PLT_OFFSET:MALLOC_PLT_OFFSET + 4] = arm64_branch(MALLOC_PLT_OFFSET, malloc_hook)
    data[REALLOC_PLT_OFFSET:REALLOC_PLT_OFFSET + 4] = arm64_branch(REALLOC_PLT_OFFSET, realloc_hook)
    data[CALLOC_PLT_OFFSET:CALLOC_PLT_OFFSET + 4] = arm64_branch(CALLOC_PLT_OFFSET, calloc_hook)
    data[POSIX_MEMALIGN_PLT_OFFSET:POSIX_MEMALIGN_PLT_OFFSET + 4] = arm64_branch(
        POSIX_MEMALIGN_PLT_OFFSET, posix_memalign_hook)
    struct.pack_into('<IIQQQQQQ', data, phoff + writable_index * phentsize,
                     *writable[:6], virtual_address - writable[3], writable[7])
    struct.pack_into('<IIQQQQQQ', data, phoff + note * phentsize,
                     1, 5, file_offset, virtual_address, virtual_address, ELF_PAGE, ELF_PAGE, ELF_PAGE)
    data.extend(b'\0' * (file_offset - len(data)))
    data.extend(payload)
    return (dict(getter_offset=XUID_GETTER_OFFSET, getter_before=XUID_GETTER_BEFORE.hex(),
                 local_user_id_sha256=hashlib.sha256(encoded).hexdigest(),
                 segment_file_offset=file_offset, segment_virtual_address=virtual_address, segment_bytes=ELF_PAGE),
            dict(talk_layer_added_offset=TALK_LAYER_ADDED_OFFSET,
                 talk_layer_added_before=TALK_LAYER_ADDED_BEFORE.hex(),
                 hook_address=hook, create_wrapper_address=create,
                 talk_finish_offset=TALK_FINISH_OFFSET,
                 talk_finish_hook_address=finish_hook,
                 script_skip_event_offset=SCRIPT_SKIP_EVENT_OFFSET,
                 script_skip_event_before=SCRIPT_SKIP_EVENT_BEFORE.hex(),
                 script_skip_event_hook_address=skip_event_hook,
                 malloc_hook_address=malloc_hook,
                 realloc_hook_address=realloc_hook,
                 calloc_hook_address=calloc_hook,
                 posix_memalign_hook_address=posix_memalign_hook,
                 allocation_counter_address=allocation_counter,
                 allocation_behavior='alternate 65-80 byte libc allocations across the 96-byte and 112-byte Scudo classes',
                 prologue_skip_destination=dict(area_id=511001003, line_id=1, rate=0.690324664115906,
                                                story_step='story_step.story_step_ch1_1'),
                 state_id=0x193,
                 behavior='preserve authored skipEvent handlers; otherwise independently clear voice, narration, talk UI, every fade layer, letterbox, camera and actor actions, restore party registration, alpha, visibility filters, idle animation and field movement, stop the active update phase, and run final cleanup'))


def patch_collabo_availability(data):
    """Extend the shared collaboration freeze cutoff without bypassing its state machine."""
    locations = ((COLLABO_FREEZE_END_AT_OFFSET, COLLABO_FREEZE_END_AT_BEFORE),
                 (COLLABO_FREEZE_EXPIRED_END_AT_OFFSET, COLLABO_FREEZE_EXPIRED_END_AT_BEFORE))
    if any(data[offset:offset + 16] != before for offset, before in locations):
        raise ValueError('Collaboration freeze end-time logic changed')
    data[COLLABO_FREEZE_END_AT_OFFSET:COLLABO_FREEZE_END_AT_OFFSET + 16] = COLLABO_FREEZE_END_AT_PATCH
    data[COLLABO_FREEZE_EXPIRED_END_AT_OFFSET:COLLABO_FREEZE_EXPIRED_END_AT_OFFSET + 16] = COLLABO_FREEZE_EXPIRED_END_AT_PATCH
    return dict(accessor_offset=COLLABO_FREEZE_END_AT_OFFSET,
                expiration_compare_offset=COLLABO_FREEZE_EXPIRED_END_AT_OFFSET,
                accessor_before=COLLABO_FREEZE_END_AT_BEFORE.hex(),
                expiration_compare_before=COLLABO_FREEZE_EXPIRED_END_AT_BEFORE.hex(),
                end_at=COLLABO_FREEZE_END_AT, end_at_utc='12025-07-06T14:59:59Z',
                extension_years=9999)


def patch_opening_lua(data):
    """Repair opening-story ownership and party visibility in the pinned Lua archive."""
    if len(data) != LUA_ZIP_BYTES or hashlib.sha256(data).hexdigest() != LUA_ZIP_SHA256:
        raise ValueError('Bundled Lua archive changed')
    evidence = client.ROOT / 'data/forevereden-evidence'
    sys.path.insert(0, str(evidence))
    try:
        from recover_master import content_key_iv, decrypt_content
    finally:
        sys.path.remove(str(evidence))
    key, iv = content_key_iv(0x173d91f, 0x173d99f)
    source = io.BytesIO(data)
    output = io.BytesIO()
    with zipfile.ZipFile(source) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if len(entries) != 67834 or len(names) != len(set(names)):
            raise ValueError('Bundled Lua member set changed')
        javascript = """
const {readFileSync}=require('node:fs');
const {createCipheriv}=require('node:crypto');
const v=JSON.parse(readFileSync(0,'utf8'));
const c=createCipheriv('aes-256-cbc',Buffer.from(v.key,'base64'),Buffer.from(v.iv,'base64'));
process.stdout.write(Buffer.concat([c.update(Buffer.from(v.data,'base64')),c.final()]));
"""
        replacements = {}
        metadata = []
        round_trips = {}
        for member, encrypted_sha, decoded_sha, expected_trailing, before, after, behavior in OPENING_LUA_PATCHES:
            encrypted = archive.read(member)
            if hashlib.sha256(encrypted).hexdigest() != encrypted_sha:
                raise ValueError(f'Opening scene Lua changed: {member}')
            decoded, trailing = decrypt_content(encrypted, key, iv, 64 * 1024)
            if (hashlib.sha256(decoded).hexdigest() != decoded_sha
                    or decoded.count(before) != 1 or trailing != expected_trailing):
                raise ValueError(f'Opening scene Lua does not match the reviewed source: {member}')
            patched = decoded.replace(before, after)
            compressed = zlib.compress(patched)
            payload = {name: base64.b64encode(value).decode() for name, value in
                       {'key': key, 'iv': iv, 'data': compressed}.items()}
            replacements[member] = subprocess.run(
                ['node', '-e', javascript], input=json.dumps(payload).encode(), capture_output=True,
                check=True, timeout=30).stdout
            round_trips[member] = (patched, bytes([16 - len(compressed) % 16])
                                              * (16 - len(compressed) % 16))
            metadata.append(dict(member=member, before_sha256=decoded_sha,
                                 after_sha256=hashlib.sha256(patched).hexdigest(),
                                 behavior=behavior))
        with zipfile.ZipFile(output, 'w') as rebuilt:
            for entry in entries:
                rebuilt.writestr(entry, replacements.get(entry.filename, archive.read(entry)))
    result = output.getvalue()
    with zipfile.ZipFile(io.BytesIO(result)) as rebuilt:
        if [entry.filename for entry in rebuilt.infolist()] != names:
            raise ValueError('Opening Lua patch changed the bundled member set')
        for member, (patched, expected_trailing) in round_trips.items():
            round_trip, trailing = decrypt_content(rebuilt.read(member), key, iv, 64 * 1024)
            if round_trip != patched or trailing != expected_trailing:
                raise ValueError(f'Opening Lua patch did not round-trip: {member}')
    return result, dict(members=metadata)


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
    output, changes, identity_patch, story_skip_patch, billing_patch, collabo_patch, opening_lua_patch = {}, [], None, None, None, None, None
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
                    collabo_patch = patch_collabo_availability(data)
                    identity_patch, story_skip_patch = patch_local_identity(data)
                    data = bytes(data)
                elif name == 'classes5.dex':
                    data = patch_local_billing(data)
                    billing_patch = dict(methods=['a0.a(setup)', 'a0.a(restoredPurchases)',
                                                  'e1.onSuccess(catalog)', 'PaymentUtil.a(country)',
                                                  'Shop.r.onSuccess(orderCatalog)', 'Shop.submit(localSuccess)',
                                                  'RequestUrl.<init>(localBase)', 'SignedRequest.onPostRequest(localTrust)'],
                                         behavior='loopback billing service with local catalog and fulfillment')
                elif name == 'assets/lua.zip':
                    data, opening_lua_patch = patch_opening_lua(data)
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
                     native_story_skip_button_patch=story_skip_patch,
                     opening_scene_visibility_patch=opening_lua_patch,
                     collabo_availability_patch=collabo_patch,
                     billing_catalog_patch=billing_patch,
                     apks=output, changes=changes, tool_sha256=client.digest(__file__),
                    removed_signing_metadata=['original JAR signatures', 'original APK signing block', 'stamp-cert-sha256'],
                    server_behavior='HTTP 503 only; game request schemas UNKNOWN',
                     active_mods=['private-billing-catalog', '9999-year-collaboration-events',
                                  'native-story-skip-button', 'opening-scene-visibility-recovery'],
                     original_account_data_copied=False)
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
