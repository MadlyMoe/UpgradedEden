"""Extract server-validation data from the exact packaged 3.17.0 master."""

import gzip
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "data" / "forevereden-evidence"
GENERATION = "ec741d3cc2f29b867892b1ed16a7a59b40e3968d"
sys.path.insert(0, str(EVIDENCE))

from check_master_sources import Reader, field, records  # noqa: E402
from recover_master import content_key_iv, decrypt_content  # noqa: E402


def text(reader, row, slot):
    return field(reader, row, slot) if slot < len(row[2]) and row[2][slot] else ""


def number(reader, row, slot, width=4):
    return field(reader, row, slot, width)


def keyed(values):
    return {str(value[0]): value[1:] for value in values}


def main():
    source = EVIDENCE / "live-content" / GENERATION / "master_data.enc"
    encrypted = source.read_bytes()
    source_hash = hashlib.sha256(encrypted).hexdigest()
    assert source_hash == "18c811dabc2a3184c81155a54a234dce64ab23e2eebac4ae1cdfde2ee76386eb"
    key, iv = content_key_iv(0x17095A5, 0x1709625)
    decoded, _ = decrypt_content(encrypted, key, iv, 512 * 1024 * 1024)
    assert hashlib.sha256(decoded).hexdigest() == "36a524831d98cbd12a087668d9c17f911bbea9cedb10bbeac14d3696262b022c"
    reader = Reader(decoded)

    gift_contents = defaultdict(list)
    for row in records(reader, 126):
        gift_contents[number(reader, row, 1)].append([text(reader, row, 2), number(reader, row, 3)])
    gifts = {}
    gift_ids = {}
    for row in records(reader, 125):
        gift_id, label = number(reader, row, 0), text(reader, row, 1)
        gifts[label] = [gift_id, gift_contents[gift_id]]
        gift_ids[str(gift_id)] = gift_contents[gift_id]

    quests = defaultdict(list)
    for row in records(reader, 98):
        quests[str(number(reader, row, 1))].append([text(reader, row, 3), number(reader, row, 4)])

    mission_ids = {text(reader, row, 1): number(reader, row, 0) for row in records(reader, 320)}
    battle_rush = {}
    for row in records(reader, 318):
        missions = []
        for index in range(4):
            mission = text(reader, row, 12 + index)
            reward = text(reader, row, 16 + index)
            if mission:
                missions.append([mission_ids[mission], reward, number(reader, row, 20 + index)])
        battle_rush[str(number(reader, row, 0))] = [number(reader, row, 3),
            [text(reader, row, 10), number(reader, row, 11)], missions]

    mission_books = defaultdict(list)
    for row in records(reader, 411):
        mission_books[number(reader, row, 1)].append(number(reader, row, 3))
    star_missions = {}
    for row in records(reader, 412):
        mission_id = number(reader, row, 0)
        star_missions[str(mission_id)] = [sorted(set(mission_books[mission_id])), text(reader, row, 18)]
    star_levels = keyed((number(reader, row, 0), text(reader, row, 4)) for row in records(reader, 414))
    star_scores = keyed((number(reader, row, 0), number(reader, row, 3)) for row in records(reader, 420))

    cat_diary = keyed((number(reader, row, 0), text(reader, row, 1), number(reader, row, 2),
        number(reader, row, 4)) for row in records(reader, 440))

    consumes = records(reader, 14)
    battle_continue = next(number(reader, row, 5, 8) for row in consumes
        if text(reader, row, 1) == "CONSUME_BATTLE_CONTINUE")
    dungeon_consumes = keyed((number(reader, row, 0), number(reader, row, 5, 8),
        number(reader, row, 6), number(reader, row, 7)) for row in consumes if row[2][6])

    def products(product_slot, content_slot, wide):
        contents = defaultdict(list)
        for row in records(reader, content_slot):
            contents[number(reader, row, 1, wide)].append([text(reader, row, 2), number(reader, row, 3)])
        result = {}
        for row in records(reader, product_slot):
            product_id = number(reader, row, 0, wide)
            result[str(product_id)] = [number(reader, row, 3), number(reader, row, 4), contents[product_id]]
        return result

    catalog = {
        "version": "3.17.0",
        "content_generation": GENERATION,
        "source_sha256": source_hash,
        "dungeons": [number(reader, row, 0) for row in records(reader, 87)],
        "dungeon_tickets": keyed((number(reader, row, 0), number(reader, row, 3)) for row in records(reader, 89)),
        "gifts": gifts,
        "gift_ids": gift_ids,
        "quests": dict(quests),
        "battle_rush": battle_rush,
        "star_library": {"missions": star_missions, "levels": star_levels, "scores": star_scores},
        "cat_diary": cat_diary,
        "consume": {"battle_continue": battle_continue, "dungeon_tickets": dungeon_consumes},
        "pc_costume_products": products(526, 527, 4),
        "pack_products": products(545, 546, 8),
    }
    counts = [len(catalog[name]) for name in ("dungeons", "dungeon_tickets", "gifts", "quests", "battle_rush", "cat_diary",
        "pc_costume_products", "pack_products")]
    assert counts == [369, 8, 3369, 1151, 96, 184, 4, 3], counts
    assert battle_continue == 50 and len(dungeon_consumes) == 10
    assert dungeon_consumes["81200101"] == (40, 564000001, 2)
    assert [len(catalog["star_library"][name]) for name in ("missions", "levels", "scores")] == [783, 80, 870]
    assert all(label in gifts for value in star_missions.values() for label in value[1:] if label)
    assert all(label in gifts for label, _, _ in cat_diary.values())
    body = json.dumps(catalog, separators=(",", ":"), sort_keys=True).encode()
    output = ROOT / "tools" / "forevereden_rewards_3_17_0.bin"
    output.write_bytes(gzip.compress(body, compresslevel=9, mtime=0))
    print(json.dumps({"output": str(output), "json_bytes": len(body), "gzip_bytes": output.stat().st_size,
        "gzip_sha256": hashlib.sha256(output.read_bytes()).hexdigest()}, indent=2))


if __name__ == "__main__":
    main()
