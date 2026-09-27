"""Read-only, exact-build ARM64 references; no client code executes."""
from pathlib import Path
import bisect
import hashlib
import io
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'data/apk-investigation' / ('linux-libs' if sys.platform == 'linux' else 'python-libs')))
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN

raw = (ROOT / 'data/apk-investigation/lib/arm64-v8a/libapp.so').read_bytes()
assert hashlib.sha256(raw).hexdigest() == '2789c0f6bb570d168a14d836a36a3e3fc372c60c63a8e79730dc9c67bc78a1dc'
elf = ELFFile(io.BytesIO(raw))
text_section = elf.get_section_by_name('.text')
code = text_section.data()
base = text_section['sh_addr']
ranges = sorted(json.loads((ROOT / 'data/apk-investigation/game-function-ranges.json').read_text()))
starts = [r[0] for r in ranges]
md = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)


def enclosing(pc):
    index = bisect.bisect_right(starts, pc) - 1
    if index >= 0 and ranges[index][0] <= pc < sum(ranges[index]):
        return ranges[index]
    return None


def readva(va, size):
    for s in elf.iter_segments():
        if s['p_type'] == 'PT_LOAD' and s['p_vaddr'] <= va and va+size <= s['p_vaddr']+s['p_filesz']:
            at = s['p_offset'] + va - s['p_vaddr']
            return raw[at:at+size]
    raise ValueError(f'Address not backed by file: {va:x}')


def disasm(pc, size=None):
    if size is None:
        pc, size = enclosing(pc)
    assert 0 < size <= 65536
    return '\n'.join(f'{i.address:x}: {i.mnemonic} {i.op_str}' for i in md.disasm(readva(pc,size),pc))


def references(needles):
    targets = {}
    for needle in needles:
        start = 0
        while (pos := raw.find(needle.encode(), start)) >= 0:
            for seg in elf.iter_segments():
                if seg['p_type'] == 'PT_LOAD' and seg['p_offset'] <= pos < seg['p_offset']+seg['p_filesz']:
                    targets[seg['p_vaddr']+pos-seg['p_offset']] = needle
            start = pos + 1
        assert start > 0
    pages = {p & ~4095 for p in targets}
    words = [w[0] for w in struct.iter_unpack('<I', code)]
    refs = []
    for i,w in enumerate(words):
        if w & 0x9f000000 != 0x90000000:
            continue
        imm = ((w>>5)&0x7ffff)*4 + ((w>>29)&3)
        if imm & (1<<20): imm -= 1<<21
        page = ((base+4*i)&~4095) + (imm<<12)
        if page not in pages:
            continue
        rd = w & 31
        for j in range(i+1,min(i+12,len(words))):
            v = words[j]
            if v & 0xffc00000 == 0x91000000 and (v>>5)&31 == rd:
                target = page + ((v>>10)&4095)
                if target in targets:
                    pc=base+4*j
                    refs.append({'string':targets[target],'string_va':hex(target),
                                 'adrp':hex(base+4*i),'reference':hex(pc),'enclosing':enclosing(pc)})
    return refs


if __name__ == '__main__':
    refs=references(['ScriptManager: luaL_loadbuffer', 'master/master_data_bundled.enc',
                     'encryption/aes_iv', 'lua.zip', 'static std::string wfs::crypto::Aes::decrypt',
                     'static std::string kmsflatbuffers::Xxtea::DecryptScalar'])
    out=Path(__file__).resolve().parent
    (out/'original-loader-references.json').write_text(json.dumps(refs,indent=2)+'\n')
    functions=sorted({tuple(r['enclosing']) for r in refs if r['enclosing']})
    (out/'original-loader-disassembly.txt').write_text('\n\n'.join(disasm(a,n) for a,n in functions))
    print(json.dumps(refs,indent=2))
