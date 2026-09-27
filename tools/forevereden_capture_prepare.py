"""Prepare the isolated capture app in rooted MuMu without copying the 11 GB asset tree."""
import argparse
import json
import re
import subprocess

import forevereden_capture_client as capture
import forevereden_client as client

ORIGINAL = client.PACKAGE
CAPTURE = capture.PACKAGE


def adb(args, *parts, input=None, timeout=180):
    process = subprocess.run([args.adb, '-s', args.serial, *parts], input=input, text=True,
                             capture_output=True, timeout=timeout)
    if process.returncode:
        raise RuntimeError((process.stderr + process.stdout)[-2000:])
    return process.stdout.strip()


def prepare(args):
    capture.verify()
    if adb(args, 'shell', 'id', '-u') != '0':
        raise ValueError('MuMu ADB root must be enabled for the isolated one-time copy')
    if adb(args, 'shell', 'getenforce') != 'Permissive':
        raise ValueError('This bounded MuMu preparation requires its existing permissive SELinux mode')
    for package in (ORIGINAL, CAPTURE):
        if 'package:' + package not in adb(args, 'shell', 'pm', 'list', 'packages', package).splitlines():
            raise ValueError(f'{package} is not installed')
    uid_match = re.fullmatch(rf'package:{re.escape(CAPTURE)} uid:(10[0-9]{{3}})',
                             adb(args, 'shell', 'cmd', 'package', 'list', 'packages', '-U', CAPTURE))
    if not uid_match:
        raise ValueError('Unexpected capture app UID')
    uid = uid_match.group(1)
    source = f'/data/user/0/{ORIGINAL}'
    destination = f'/data/user/0/{CAPTURE}'
    assets = f'/data/user/0/{ORIGINAL}/files/contents'
    script = f'''set -eu
src={source}
dst={destination}
assets={assets}
am force-stop {ORIGINAL}; am force-stop {CAPTURE}
umount "$dst/files/contents" 2>/dev/null || true
rm -rf "$dst/cache" "$dst/code_cache" "$dst/databases" "$dst/shared_prefs" "$dst/no_backup" "$dst/files"
for name in databases shared_prefs no_backup; do [ ! -e "$src/$name" ] || cp -a "$src/$name" "$dst/"; done
mkdir -p "$dst/files"
for item in "$src/files"/* "$src/files"/.[!.]* "$src/files"/..?*; do
  [ -e "$item" ] || continue
  [ "${{item##*/}}" = contents ] && continue
  cp -a "$item" "$dst/files/"
done
chown -R {uid}:{uid} "$dst"
restorecon -RF "$dst" 2>/dev/null || true
chmod -R a+rX "$assets"
mkdir -p "$dst/files/contents"
chown {uid}:{uid} "$dst/files/contents"
mount -o bind "$assets" "$dst/files/contents"
'''
    adb(args, 'shell', 'sh', '-s', input=script, timeout=300)
    mountinfo = adb(args, 'shell', 'cat', '/proc/self/mountinfo')
    if not any(line.split()[4] == f'{destination}/files/contents' for line in mountinfo.splitlines() if len(line.split()) > 5):
        raise ValueError('Capture asset bind mount did not publish')
    source_hash = adb(args, 'shell', 'md5sum', f'{assets}/1/project.manifest').split()[0]
    target_hash = adb(args, 'shell', 'md5sum', f'{destination}/files/contents/1/project.manifest').split()[0]
    if source_hash != target_hash:
        raise ValueError('Capture asset view differs from the original client')
    print(json.dumps(dict(package=CAPTURE, uid=int(uid), official_state_copied=True,
                          asset_storage='bind-mounted original content', asset_manifest_md5=target_hash)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare',))
    parser.add_argument('--adb', default=r'C:\Main\Productivity\Coding\Android\Sdk\platform-tools\adb.exe')
    parser.add_argument('--serial', default='10.0.2.207:5555')
    prepare(parser.parse_args())
