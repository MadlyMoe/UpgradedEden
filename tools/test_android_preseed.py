"""Small offline regression check; does not contact or alter a device."""
import json
from pathlib import Path
import tempfile

from android_preseed import VERSION, CDN, ROOT, assets, batches, safe_path, transfer_url


assert safe_path('files/sound/voice/test.ogg') == 'files/sound/voice/test.ogg'
for bad in ('../save', '/absolute', 'files/../save', 'files//save', 'files\\save',
            'files/%2e%2e/save', 'files/x\nurl=evil', 'files/"x', 'files/$(id)'):
    try:
        safe_path(bad)
        raise AssertionError('unsafe path accepted')
    except ValueError:
        pass
assert [len(b) for b in batches([{'size': 1}] * 513)] == [512, 1]
assert [len(b) for b in batches([{'size': 80 * 1024**2}] * 2)] == [1, 1]
row = dict(path='1/files/a b.ogg', md5='a'*32, url=CDN+'/pinned/a.ogg')
assert transfer_url(row,{}) == row['url']
assert transfer_url(row,{row['path']:'b'*32}) == row['url']
assert transfer_url(row,{row['path']:row['md5']}) == 'file://'+ROOT+'/1/files/a%20b.ogg'
with tempfile.TemporaryDirectory() as tmp:
    folder = Path(tmp)
    for phase in range(1, 17):
        m = dict(version=VERSION, packageUrl=CDN,
                 remoteManifestUrl=f'{CDN}/{VERSION}/pkm/production-global-us/project.manifest.{phase}',
                 assets={'files/test.ogg': dict(path='version/contents/files/test.ogg', size=8, md5='a' * 32),
                         'files/movie_pc/test.usm': dict(path='version/contents/files/movie_pc/test.usm', size=9, md5='b' * 32)})
        (folder / f'{phase}-project.manifest.temp.json').write_text(json.dumps(m))
    rows, pins = assets(folder)
    assert len(rows) == len(pins) == 16 and rows[0]['path'] == '1/files/test.ogg'
    rows, pins = assets(folder, [1])
    assert len(rows) == len(pins) == 1 and rows[0]['path'] == '1/files/test.ogg'
    ap = m | {'packageUrl': CDN[:-2] + 'ap',
              'remoteManifestUrl': f'{CDN[:-2]}ap/{VERSION}/pkm/production-global-ap/project.manifest.1'}
    (folder / '1-project.manifest.temp.json').write_text(json.dumps(ap))
    rows, pins = assets(folder, [1], 'ap')
    assert rows[0]['url'].startswith(CDN[:-2] + 'ap/')
    path = folder / '1-project.manifest.temp.json'
    m['version'] = 'wrong-generation'
    path.write_text(json.dumps(m))
    try:
        assets(folder)
        raise AssertionError('wrong generation accepted')
    except ValueError:
        pass
    control = folder / 'guest.sh'
    control.write_text('set -eu\necho checked\n', newline='\n')
    assert control.read_bytes() == b'set -eu\necho checked\n'
print('PASS: path boundary, batch bounds, exact generation, PC movie exclusion, LF guest control files')
