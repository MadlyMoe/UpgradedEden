"""Create a maxed roster on top of ForeverEden's untouched starter progress."""

import argparse
from collections import Counter
import copy
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "data" / "forevereden-evidence"
GENERATION = "ec741d3cc2f29b867892b1ed16a7a59b40e3968d"
MASTER_SHA256 = "18c811dabc2a3184c81155a54a234dce64ab23e2eebac4ae1cdfde2ee76386eb"
DECODED_SHA256 = "36a524831d98cbd12a087668d9c17f911bbea9cedb10bbeac14d3696262b022c"
PROFILE_NAME = "debug maxed"
GAME_NAME = "DebugMaxed"
LEVEL_80_EXP = 56_490_053
LEVEL_100_EXP = 1_132_563_972
INTERNAL_PC_NAMESPACES = {1013, 1015, 1016, 1017, 1018}
WEAPON_COPIES = 6
ARMOR_COPIES = 6
BADGE_COPIES = 12
GRASTA_COPIES = 24
GRASTA_MAX_REFINING_LEVEL = 2
ORE_AMOUNT = 100

sys.path.insert(0, str(EVIDENCE))
from check_master_sources import Reader, field, records  # noqa: E402
from recover_master import content_key_iv, decrypt_content  # noqa: E402


def value(reader, row, slot, width=4):
    return field(reader, row, slot, width)


def object_id(kind, identifier):
    return hashlib.sha256(f"{PROFILE_NAME}:{kind}:{identifier}".encode()).hexdigest()[:24]


def rewrite_user_id(value_, user_id):
    if isinstance(value_, dict):
        return {key: user_id if key == "userId" else rewrite_user_id(item, user_id)
                for key, item in value_.items()}
    if isinstance(value_, list):
        return [rewrite_user_id(item, user_id) for item in value_]
    return value_


def skill_slots(reader, style):
    skills = {1: value(reader, style, 33), 2: 109900001, 3: value(reader, style, 30),
              5: value(reader, style, 9), 6: value(reader, style, 30)}
    types = {1: 1, 2: 2, 3: 3, 4: 3, 5: 4, 6: 5, 7: 6, 8: 3, 9: 3}
    return [{"skillSlotNumber": slot, "slotSkillType": types[slot], "skillId": skills.get(slot, 0),
             "signature": 0, "updatedAt": 0} for slot in range(1, 10)]


def max_vc_level(reader, style):
    skills = [value(reader, style, slot) for slot in (30, 31, 32)]
    if any(not skills[index] and any(skills[index + 1:]) for index in range(2)):
        raise ValueError(f"Invalid variable chant progression: {skills}")
    return max(1, next((index for index, skill in enumerate(skills, 1) if not skill), 4) - 1)


def orb_slots():
    return [{"slotNumber": slot, "equipmentStockId": 0, "updatedAt": 0} for slot in range(1, 6)]


def equipment_stock(user_id, stock_id, equipment_id, refining_level=0, bonus1=0, bonus2=0):
    return {
        "_id": object_id("equipment-stock", stock_id), "userId": user_id, "id": stock_id,
        "equipmentId": equipment_id, "durability": 0, "badgeStatusBonusPower1": bonus1,
        "badgeStatusBonusPower2": bonus2, "signature": 0, "refiningLevel": refining_level,
        "equippingPcId": 0, "unknownEquipmentId": 0, "unknownEquipmentStockId": 0,
        "isLocked": False, "updatedAt": 0,
    }


def equipment_specie(user_id, equipment_id):
    return {
        "_id": object_id("equipment-specie", equipment_id), "userId": user_id,
        "equipmentId": equipment_id, "reservedAmount": 0, "craftingState": 3,
        "bookEntryState": 3, "signature": 0, "updatedAt": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--starter", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--donor", type=Path, help="Optional captured profile; stdin is used when omitted")
    args = parser.parse_args()

    starter = json.loads(args.starter.read_text(encoding="utf-8"))
    donor = json.loads(args.donor.read_text(encoding="utf-8") if args.donor else sys.stdin.read())
    if len(starter.get("tables", {})) != 207 or len(donor.get("tables", {})) != 207:
        raise ValueError("Expected complete 207-table ForeverEden profiles")

    encrypted = (EVIDENCE / "live-content" / GENERATION / "master_data.enc").read_bytes()
    if hashlib.sha256(encrypted).hexdigest() != MASTER_SHA256:
        raise ValueError("Frozen 3.17.0 master mismatch")
    key, iv = content_key_iv(0x17095A5, 0x1709625)
    decoded, _ = decrypt_content(encrypted, key, iv, 512 * 1024 * 1024)
    if hashlib.sha256(decoded).hexdigest() != DECODED_SHA256:
        raise ValueError("Decoded 3.17.0 master mismatch")
    reader = Reader(decoded)

    characters = {value(reader, row, 0): row for row in records(reader, 18)}
    pc_ids = {pc_id for pc_id, row in characters.items()
              if pc_id % 10 == 1 and value(reader, row, 3) < 99_999
              and pc_id // 100_000 not in INTERNAL_PC_NAMESPACES}
    styles = {value(reader, row, 0): row for row in records(reader, 189)
              if value(reader, row, 2) in pc_ids}
    styles_by_pc = {}
    for style_id, row in styles.items():
        styles_by_pc.setdefault(value(reader, row, 2), []).append((style_id, row))
    vc_levels = {style_id: max_vc_level(reader, row) for style_id, row in styles.items()}

    panels_by_job = {}
    for row in records(reader, 22):
        panels_by_job.setdefault(value(reader, row, 1), []).append(value(reader, row, 0))

    zodiac_rows = list(records(reader, 424))
    zodiac_style_ids = {value(reader, row, 2) for row in zodiac_rows}
    zodiac_panels = {}
    for row in records(reader, 425):
        zodiac_panels.setdefault(value(reader, row, 1), []).append(value(reader, row, 0))

    weapon_rows = {value(reader, row, 0): row for row in records(reader, 41)}
    armor_ids = {value(reader, row, 0) for row in records(reader, 44)}
    badge_rows = {value(reader, row, 0): row for row in records(reader, 46)}
    element_badge_ids = {value(reader, row, 0) for row in records(reader, 358)}
    grasta_rows = {value(reader, row, 0): row for row in records(reader, 231)
                   if "_test" not in field(reader, row, 2)}
    ore_ids = {value(reader, row, 0) for row in records(reader, 260)
               if field(reader, row, 1).startswith("generic_item.orb_processing_item_")}

    weapon_by_label = {field(reader, row, 5): equipment_id
                       for equipment_id, row in weapon_rows.items() if field(reader, row, 5)}
    grow_up_by_group = {}
    for row in records(reader, 223):
        grow_up_by_group.setdefault(field(reader, row, 9), []).append(
            (field(reader, row, 1), field(reader, row, 2)))
    true_awakened_weapon_ids = set()
    for row in records(reader, 361):
        group = field(reader, row, 2)
        chain = grow_up_by_group.get(group, [])
        labels = {label for edge in chain for label in edge if label}
        terminals = [source for source, destination in chain if source and not destination]
        if len(terminals) != 1 or any(label not in weapon_by_label for label in labels):
            raise ValueError(f"Invalid personal weapon chain: {group}")
        true_awakened_weapon_ids.add(weapon_by_label[terminals[0]])

    if (len(pc_ids), len(styles), len(zodiac_rows)) != (247, 377, 150):
        raise ValueError("Unexpected frozen-master roster")
    if set(styles_by_pc) != pc_ids:
        raise ValueError("A playable character has no style")
    if (len(grasta_rows), len(ore_ids), len(element_badge_ids), len(true_awakened_weapon_ids)) != (1824, 63, 40, 57):
        raise ValueError("Unexpected frozen-master equipment inventory")

    user_id = 900_000_000_000 + int(hashlib.sha256(PROFILE_NAME.encode()).hexdigest()[:8], 16)
    profile = rewrite_user_id(copy.deepcopy(starter), user_id)
    profile["user_id"] = user_id
    profile["profile_name"] = PROFILE_NAME
    profile["source_scope"] = "3.17.0 debug-maxed roster and inventory on untouched starter story progress"
    profile["tables"]["UserInfo"]["name"] = GAME_NAME

    user_styles = []
    for style_id, row in sorted(styles.items()):
        pc_id = value(reader, row, 2)
        jobs = [value(reader, row, slot) for slot in range(4, 8)]
        job_rank = max(rank for rank, job in zip(range(2, 6), jobs) if job)
        user_styles.append({
            "_id": object_id("style", style_id), "userId": user_id, "pcStyleId": style_id, "pcId": pc_id,
            "totalExp": LEVEL_100_EXP if style_id in zodiac_style_ids else LEVEL_80_EXP,
            "vcLevel": vc_levels[style_id], "jobRank": job_rank, "portraitJobRank": job_rank,
            "skillSlots": skill_slots(reader, row), "state": 2, "signature": 0,
            "jobRankCount2": int(job_rank == 2), "jobRankCount3": int(job_rank == 3),
            "jobRankCount4": int(job_rank == 4), "jobRankCount5": int(job_rank == 5),
            "extraPersonalAbilityId": 0, "extraSpineAttachmentId": 0,
            "weaponEquipmentStockId": 0, "armorEquipmentStockId": 0, "badgeEquipmentStockId": 0,
            "additionalBadgeEquipmentStockId": 0, "pcAbilityOrbSlot": orb_slots(), "pcRuneSlot": [],
            "pcCostumeId": 0, "updatedAt": 0,
        })

    donor_pcs = {row["pcId"]: row for row in donor["tables"]["UserPC"]}
    user_pcs = []
    for pc_id in sorted(pc_ids):
        character = characters[pc_id]
        pc_styles = sorted(styles_by_pc[pc_id])
        active_style_id, active_style = next(((style_id, row) for style_id, row in pc_styles
                                               if style_id in zodiac_style_ids), pc_styles[0])
        source = donor_pcs.get(pc_id, {})
        max_exp = LEVEL_100_EXP if any(style_id in zodiac_style_ids for style_id, _ in pc_styles) else LEVEL_80_EXP
        hp = source.get("hpMaxCache") or value(reader, character, 28)
        mp = source.get("mpMaxCache") or value(reader, character, 34)
        user_pcs.append({
            "_id": object_id("pc", pc_id), "userId": user_id, "pcId": pc_id, "totalExp": max_exp,
            "hp": hp, "mp": mp, "destinyPoint": 255,
            "weaponEquipmentStockId": 0, "armorEquipmentStockId": 0, "badgeEquipmentStockId": 0,
            "variableChantLevel": vc_levels[active_style_id], "jobRank": 2, "jobSlots": [],
            "skillSlots": skill_slots(reader, active_style), "abilityPoint": 999, "bookEntryState": 4,
            "signature": 0, "joiningState": 1, "displayNameTag": None, "pcStyleId": active_style_id,
            "pcAbilityOrbSlot": orb_slots(), "additionalBadgeEquipmentStockId": 0, "equipmentState": 1,
            "hpMaxCache": hp, "mpMaxCache": mp, "lockedAbilityIds": [], "updatedAt": 0,
        })

    user_jobs = []
    for pc_id in sorted(pc_ids):
        job_ids = sorted({value(reader, row, slot) for _, row in styles_by_pc[pc_id] for slot in range(4, 8)
                          if value(reader, row, slot)})
        user_jobs.append({
            "_id": object_id("jobs", pc_id), "userId": user_id, "pcId": pc_id,
            "pcJobs": [{"pcJobId": job_id,
                        "abilityPanels": [{"pcAbilityPanelId": panel_id, "state": 3, "signature": 0,
                                           "assignedAbilityId": 0, "updatedAt": 0}
                                          for panel_id in sorted(panels_by_job.get(job_id, []))],
                        "signature": 0, "updatedAt": 0} for job_id in job_ids],
            "updatedAt": 0,
        })

    user_zodiacs = []
    for row in zodiac_rows:
        zodiac_id = value(reader, row, 0)
        user_zodiacs.append({
            "_id": object_id("zodiac", zodiac_id), "userId": user_id, "pcStyleZodiacId": zodiac_id,
            "signature": 0,
            "zodiacPanels": [{"pcZodiacPanelId": panel_id, "state": 3, "updatedAt": 0}
                              for panel_id in sorted(zodiac_panels[zodiac_id])],
            "awakeStep": 3, "isEarlyOwnerBonusProcessed": True, "updatedAt": 0,
        })

    species_by_id = {row["equipmentId"]: rewrite_user_id(copy.deepcopy(row), user_id)
                     for row in donor["tables"]["UserEquipmentSpecie"]}
    weapon_ids = set(weapon_rows)
    badge_ids = set(badge_rows)
    for equipment_id in weapon_ids | armor_ids | badge_ids | set(grasta_rows) | element_badge_ids:
        species_by_id.setdefault(equipment_id, equipment_specie(user_id, equipment_id))

    initial_equipment = {row["id"]: row["equipmentId"] for row in donor["tables"]["UserEquipmentStock"]
                         if 1 <= row["id"] <= 12}
    if (set(initial_equipment) != set(range(1, 13))
            or any(initial_equipment[index] // 1_000_000 != 211 for index in range(1, 9))
            or any(initial_equipment[index] // 1_000_000 != 217 for index in range(9, 12))
            or initial_equipment[12] // 1_000_000 != 281):
        raise ValueError("Donor does not contain the frozen client's initial equipment stocks")
    user_equipment = [equipment_stock(user_id, stock_id, initial_equipment[stock_id])
                      for stock_id in range(1, 13)]
    equipment_counts = Counter(row["equipmentId"] for row in user_equipment)
    stock_id = 13
    for equipment_id in sorted(weapon_ids - true_awakened_weapon_ids):
        for _ in range(WEAPON_COPIES - equipment_counts[equipment_id]):
            user_equipment.append(equipment_stock(user_id, stock_id, equipment_id))
            stock_id += 1
    for equipment_id in sorted(true_awakened_weapon_ids):
        for _ in range(1 - equipment_counts[equipment_id]):
            user_equipment.append(equipment_stock(user_id, stock_id, equipment_id))
            stock_id += 1
    for equipment_id in sorted(armor_ids):
        for _ in range(ARMOR_COPIES - equipment_counts[equipment_id]):
            user_equipment.append(equipment_stock(user_id, stock_id, equipment_id))
            stock_id += 1
    for equipment_id in sorted(badge_ids):
        row = badge_rows[equipment_id]
        bonus1, bonus2 = value(reader, row, 10), value(reader, row, 13)
        for _ in range(BADGE_COPIES - equipment_counts[equipment_id]):
            user_equipment.append(equipment_stock(user_id, stock_id, equipment_id,
                                                   bonus1=bonus1, bonus2=bonus2))
            stock_id += 1

    user_grasta = []
    grasta_stock_id = stock_id
    for equipment_id in sorted(grasta_rows):
        for _ in range(GRASTA_COPIES):
            user_grasta.append({
                "_id": object_id("grasta-stock", grasta_stock_id), "userId": user_id,
                "id": grasta_stock_id, "equipmentId": equipment_id, "signature": 0,
                "refiningLevel": GRASTA_MAX_REFINING_LEVEL, "equippingPcId": 0,
                "processedItemId": 0, "updatedAt": 0,
            })
            grasta_stock_id += 1

    user_element_badges = []
    element_badge_stock_id = grasta_stock_id
    for equipment_id in sorted(element_badge_ids):
        for _ in range(BADGE_COPIES):
            user_element_badges.append({
                "_id": object_id("element-badge-stock", element_badge_stock_id), "userId": user_id,
                "id": element_badge_stock_id, "equipmentId": equipment_id,
                "signature": 0, "updatedAt": 0,
            })
            element_badge_stock_id += 1

    generic_items = {row["genericItemId"]: row for row in profile["tables"]["UserGenericItem"]}
    for generic_item_id in sorted(ore_ids):
        generic_items[generic_item_id] = {
            "_id": object_id("generic-item", generic_item_id), "userId": user_id,
            "genericItemId": generic_item_id, "amount": ORE_AMOUNT, "reservedAmount": 0,
            "bookEntryState": 3, "signature": 0, "updatedAt": 0,
        }

    profile["tables"]["UserPC"] = user_pcs
    profile["tables"]["UserPCStyle"] = user_styles
    profile["tables"]["UserPCJobSet"] = user_jobs
    profile["tables"]["UserPCStyleZodiac"] = user_zodiacs
    profile["tables"]["UserEquipmentSpecie"] = [species_by_id[equipment_id]
                                                    for equipment_id in sorted(species_by_id)]
    profile["tables"]["UserEquipmentStock"] = user_equipment
    profile["tables"]["UserEquipmentStockOfAbilityOrb"] = user_grasta
    profile["tables"]["UserEquipmentStockOfElementBadge"] = user_element_badges
    profile["tables"]["UserGenericItem"] = [generic_items[item_id] for item_id in sorted(generic_items)]
    profile["tables"]["UserInfo"]["lastEquipmentStockId"] = element_badge_stock_id - 1

    final_equipment_counts = Counter(row["equipmentId"] for row in user_equipment)
    stock_ids = [{row["id"] for row in rows} for rows in
                 (user_equipment, user_grasta, user_element_badges)]
    if not (all(row["destinyPoint"] == 255 for row in user_pcs)
            and all(row["state"] == 2 for row in user_styles)
            and all(row["vcLevel"] == vc_levels[row["pcStyleId"]] for row in user_styles)
            and all(row["variableChantLevel"] == vc_levels[row["pcStyleId"]] for row in user_pcs)
            and all(panel["state"] == 3 for row in user_jobs for job in row["pcJobs"]
                    for panel in job["abilityPanels"])
            and all(row["awakeStep"] == 3 and all(panel["state"] == 3 for panel in row["zodiacPanels"])
                    for row in user_zodiacs)
            and all(final_equipment_counts[equipment_id] == WEAPON_COPIES
                    for equipment_id in weapon_ids - true_awakened_weapon_ids)
            and all(final_equipment_counts[equipment_id] == 1 for equipment_id in true_awakened_weapon_ids)
            and all(final_equipment_counts[equipment_id] == ARMOR_COPIES for equipment_id in armor_ids)
            and all(final_equipment_counts[equipment_id] == BADGE_COPIES for equipment_id in badge_ids)
            and len(user_grasta) == len(grasta_rows) * GRASTA_COPIES
            and all(row["refiningLevel"] == GRASTA_MAX_REFINING_LEVEL for row in user_grasta)
            and all(generic_items[item_id]["amount"] == ORE_AMOUNT for item_id in ore_ids)
            and not any(stock_ids[left] & stock_ids[right] for left, right in ((0, 1), (0, 2), (1, 2)))
            and profile["tables"]["UserInfo"]["lastEquipmentStockId"] ==
                max(stock_id for ids in stock_ids for stock_id in ids)):
        raise AssertionError("Maxed profile validation failed")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(profile, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "profile_name": PROFILE_NAME, "user_id": user_id,
                      "characters": len(user_pcs), "styles": len(user_styles),
                      "stellar_awakened": len(user_zodiacs), "story_steps": len(profile["tables"]["UserStoryStep"]),
                      "quests": len(profile["tables"]["UserQuest"]),
                      "equipment_stocks": len(user_equipment), "true_awakened_weapons": len(true_awakened_weapon_ids),
                      "grasta_types": len(grasta_rows), "grasta_stocks": len(user_grasta),
                      "element_badge_stocks": len(user_element_badges), "grasta_ores": len(ore_ids)}))


if __name__ == "__main__":
    main()
