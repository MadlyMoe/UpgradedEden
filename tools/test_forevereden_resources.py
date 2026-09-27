"""Bounds check for the resource overlay's original-file inventory."""
from forevereden_resources import parse_inventory, verify_inventory, verify_preload
from android_preseed import VERSION

digest = 'a'*32
assert parse_inventory(digest+'  ./files/a b.pkm\n') == {'files/a b.pkm':digest}
for bad in (digest+'  ../outside', digest+'  ./files/../outside',
            digest+'  ./files//a', 'z'*32+'  ./files/a',
            digest+'  ./files/a\n'+digest+'  ./files/a'):
    try:
        parse_inventory(bad)
    except ValueError:
        pass
    else:
        raise AssertionError('Accepted unsafe or duplicate inventory')
verify_inventory({'1/files/a':digest},[{'path':'1/files/a','md5':digest}])
for inventory in ({},{'1/files/a':'b'*32}):
    try:
        verify_inventory(inventory,[{'path':'1/files/a','md5':digest}])
    except ValueError:
        pass
    else:
        raise AssertionError('Accepted missing or corrupt resource')
record = dict(complete=True, package='games.fed.anothereden', private_client_runtime_id='pinned',
              version=VERSION, phases=[1], manifest_sha256={'manifest':'hash'}, verified_files=1,
              verified_bytes=8, owner='10053:10053')
def check(value):
    verify_preload(value,'pinned',[1],[{'size':8}],{'manifest':'hash'},'10053:10053')
check(record)
for key,value in [('complete',False),('package','games.wfs.anothereden'),('verified_files',0),
                  ('verified_bytes',9),('manifest_sha256',{}),('private_client_runtime_id','other')]:
    try:
        check(record | {key:value})
    except ValueError:
        pass
    else:
        raise AssertionError('Accepted incomplete or mismatched preload')
print('PASS: bounded paths, duplicate rejection, exact original asset identity and permanent preload gate')
