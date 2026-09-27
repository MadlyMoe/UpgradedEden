"""Focused preservation/boundary checks; no device or network is used."""
from pathlib import Path
import hashlib
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import forevereden_client as client


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    payload = root / 'base.apk'
    payload.write_bytes(b'original')
    expected = {'base.apk': (8, hashlib.sha256(b'original').hexdigest())}
    client.validate_payload(root, expected)
    payload.write_bytes(b'modified')
    try:
        client.validate_payload(root, expected)
        raise AssertionError('Tampering was accepted')
    except ValueError:
        pass
    identity = {'active_mods': [], 'schema': 1}
    assert client.identity_digest(identity) == client.identity_digest({'schema': 1, 'active_mods': []})
    assert client.identity_digest(identity) != client.identity_digest({**identity, 'schema': 2})
    client.atomic_json(root / 'identity.json', identity)
    assert client.json.loads((root / 'identity.json').read_text()) == identity

args = SimpleNamespace(adb='adb', serial='test-device')
manifest = {'runtime_id': 'test'}
with patch.object(client, 'verify', return_value=(manifest, Path('.'))), patch.object(client, 'adb') as fake:
    fake.side_effect = ['arm64-v8a', 'package:' + client.PACKAGE, 'package:/data/app/base.apk']
    try:
        client.device(args, 'install')
        raise AssertionError('Existing app was overwritten')
    except ValueError as exc:
        assert 'already installed' in str(exc)
    assert all('install-multiple' not in call.args for call in fake.call_args_list)
with patch.object(client, 'verify', return_value=(manifest, Path('.'))), patch.object(client, 'adb') as fake:
    fake.return_value = 'x86_64'
    try:
        client.device(args, 'install')
        raise AssertionError('Wrong ABI was accepted')
    except ValueError:
        pass
with patch.object(client.subprocess, 'run') as run:
    try:
        client.adb(SimpleNamespace(adb='adb', serial=None), 'shell', 'true')
        raise AssertionError('Implicit device targeting was allowed')
    except ValueError:
        pass
    run.assert_not_called()
with patch.object(client.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stdout=b'', stderr=b'')):
    try:
        client.adb(args, 'shell', 'pidof', client.PACKAGE)
        raise AssertionError('Failed ADB command was accepted')
    except RuntimeError as exc:
        assert 'exit code 1' in str(exc)
for bad_output in ['Status: timeout', 'Starting: Intent only']:
    with patch.object(client, 'verify', return_value=(manifest, Path('.'))), patch.object(client, 'adb') as fake:
        fake.side_effect = ['arm64-v8a', 'package:' + client.PACKAGE,
                            '\n'.join('package:/data/app/' + name for name in client.APKS),
                            *[sha + ' ignored' for _, sha in client.APKS.values()], bad_output]
        try:
            client.device(args, 'launch')
            raise AssertionError('Unconfirmed launch was accepted')
        except RuntimeError:
            pass
with patch.object(client, 'verify', return_value=(manifest, Path('.'))), patch.object(client, 'adb') as fake:
    fake.side_effect = ['arm64-v8a', 'package:' + client.PACKAGE,
                        'package:/data/app/base.apk', '0' * 64 + ' base.apk']
    try:
        client.device(args, 'launch')
        raise AssertionError('Modified installed APK was launched')
    except ValueError as exc:
        assert 'Installed APK bytes differ' in str(exc)
    assert all('start' not in call.args for call in fake.call_args_list)
print('PASS: identity, payload and installed-APK tamper rejection, atomic manifest, existing-app preservation, ABI, explicit device targeting, and confirmed launch status')
