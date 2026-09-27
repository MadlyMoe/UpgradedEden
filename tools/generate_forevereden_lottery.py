"""Extract the exact 3.17.0 banner layouts and weighted stock pools."""

import gzip
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "data" / "forevereden-evidence"
sys.path.insert(0, str(EVIDENCE))

from check_master_sources import Reader, field  # noqa: E402
from recover_master import content_key_iv, decrypt_content  # noqa: E402


def rows(reader, slot):
    root = reader.read("<I", 0)
    fields = reader.table(root)[3]
    at = root + fields[slot]
    vector = at + reader.read("<I", at)
    for index in range(reader.read("<I", vector)):
        pointer = vector + 4 + index * 4
        record = pointer + reader.read("<I", pointer)
        _, _, size, record_fields = reader.table(record)
        yield record, size, record_fields


def main():
    encrypted = (EVIDENCE / "live-content" / "ec741d3cc2f29b867892b1ed16a7a59b40e3968d" / "master_data.enc").read_bytes()
    source_hash = hashlib.sha256(encrypted).hexdigest()
    assert source_hash == "18c811dabc2a3184c81155a54a234dce64ab23e2eebac4ae1cdfde2ee76386eb"
    key, iv = content_key_iv(0x17095A5, 0x1709625)
    decoded, _ = decrypt_content(encrypted, key, iv, 512 * 1024 * 1024)
    assert hashlib.sha256(decoded).hexdigest() == "36a524831d98cbd12a087668d9c17f911bbea9cedb10bbeac14d3696262b022c"
    reader = Reader(decoded)

    banners = {}
    for row in rows(reader, 29):
        banner_id = field(reader, row, 0, 4)
        banners[str(banner_id)] = [field(reader, row, slot, 4) for slot in (4, 5, 7, 8, 9, 10, 11)]
    group_ids = {value[4] for value in banners.values() if value[4]} | {value[6] for value in banners.values() if value[6]}
    pools = {str(group_id): [] for group_id in group_ids}
    rarity_counts = {}
    for index, row in enumerate(rows(reader, 31)):
        group_id = field(reader, row, 1, 4)
        if group_id in group_ids:
            stock = [field(reader, row, 9, 8), field(reader, row, 2, 4), field(reader, row, 3, 4), field(reader, row, 5, 4)]
            if stock[0] <= 0 or stock[1] <= 0 or stock[3] < 0:
                raise ValueError(f"Invalid lottery stock {stock}")
            pools[str(group_id)].append(stock)
            rarity_counts[stock[2]] = rarity_counts.get(stock[2], 0) + 1
        if index and index % 50000 == 0:
            print(f"decoded {index} lottery stocks", flush=True)

    assert len(banners) == 3352 and len(pools) == 1334
    assert sum(map(len, pools.values())) == 353341 and all(pools.values())
    zero_rate_pools = [group_id for group_id, pool in pools.items() if sum(stock[3] for stock in pool) == 0]
    catalog = {"version": "3.17.0", "source_sha256": source_hash, "banners": banners, "pools": pools}
    body = json.dumps(catalog, separators=(",", ":"), sort_keys=True).encode()
    output = ROOT / "tools" / "forevereden_lottery_3_17_0.bin"
    output.write_bytes(gzip.compress(body, compresslevel=9, mtime=0))
    print(json.dumps({"output": str(output), "banners": len(banners), "pools": len(pools),
        "stocks": sum(map(len, pools.values())), "rarities": rarity_counts, "zero_rate_pools": zero_rate_pools,
        "json_bytes": len(body),
        "gzip_bytes": output.stat().st_size, "gzip_sha256": hashlib.sha256(output.read_bytes()).hexdigest()}, indent=2))


if __name__ == "__main__":
    main()
