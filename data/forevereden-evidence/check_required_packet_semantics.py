"""Pin proven semantics for required 3.17.0 gameplay packets.

Passing this check does not make an endpoint supported.  It proves only the
client-side request, response and state transitions listed in the output; the
server must still implement every listed mutation atomically and persist it.
"""

import json
import struct
from pathlib import Path

import native_refs as n
from network_action_inventory import REQUEST_FIELD_REFERENCES, REQUEST_FIELDS, referenced_string
from network_trace import trace


OUT = Path(__file__).with_name("required-packet-semantics.json")

PARSERS = {
    "UserBattleRushCourse": (0x3A57074, {"userId", "battleRushCourseId", "state", "signature"}),
    "UserBattleRushStage": (0x3A5A590, {"userId", "battleRushStageId", "battleRushCourseId", "lastOpenDateTime",
        "lastEnterDateTime", "state", "missions", "signature"}),
    "UserBattleRushWave": (0x3A5BB4C, {"userId", "battleRushWaveId", "state"}),
    "UserRoguelikeDungeon": (0x3A7C6C0, {"userId", "dungeonId", "position", "isSuspended", "nowFloorDepth",
        "maxFloorDepth", "floorTotalMoveDistance", "isDefeatedAreaEnemy"}),
    "UserStarLibraryBookStatus": (0x3A97CA0, {"userId", "bookId", "state", "linkList"}),
    "UserStarLibraryMissionStatus": (0x3A9AAF0, {"userId", "missionId", "bookId", "position", "state",
        "taskList", "counter"}),
    "UserStarLibraryLevel": (0x3A9C020, {"userId", "starLibraryLevelId", "state"}),
    "UserStarLibraryScoreAttackInfo": (0x3A9FC40, {"userId", "starLibraryScoreAttackInfoId", "state",
        "highScore", "totalDamage", "totalActivityBonus", "totalAFBonus", "totalPartyBonus", "highScoreParty"}),
    "UserStarLibraryScoreAttackReward": (0x3AA0E3C, {"userId", "starLibraryScoreAttackRewardId", "state"}),
    "UserCatDiary": (0x3AAB290, {"userId", "level", "slotCat", "termId", "touchedAt"}),
    "UserCatDiaryChain": (0x3AAEB34, {"userId", "id", "slotNo", "step", "catDiaryLocationId", "lotteryDt"}),
    "UserCatDiaryStatus": (0x3AB05E8, {"userId", "rewardTotal", "stampCount", "stampTotal", "stampStatus",
        "stampResetAt", "rewardCount"}),
    "UserGift": (0x39FABB0, {"userId", "id", "senderType", "senderId", "title", "message", "contents",
        "giftAcquiredType", "receiveType", "startAt", "expireAt", "state", "createdAt", "securityToken",
        "userOdealAchievementId"}),
    "UserPackProduct": (0x3AF446C, {"userId", "packProductId", "count"}),
    "UserPCCostume": (0x3AE9FD4, {"userId", "costumeId", "status"}),
    "UserPCCostumeProduct": (0x3AEBCE0, {"userId", "costumeProductId", "count"}),
}

OPERATION_TYPES = (1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000, 12000, 15000,
    16000, 14000, 17000, 18000, 19000, 20000, 21000, 22000, 23000, 24000, 25000, 26000)
OPERATION_HANDLERS = {
    1000: 0x34F4B00, 2000: 0x373E7FC, 3000: 0x3967C40, 4000: 0x39678CC, 5000: 0x37AF82C,
    7000: 0x3328F68, 8000: 0x3712DA4, 12000: 0x3712E7C, 15000: 0x33299B4, 16000: 0x383A788,
    14000: 0x371EAC8, 17000: 0x32C8F48, 18000: 0x38C586C, 19000: 0x32CC8E4, 20000: 0x32CD378,
    21000: 0x36F9734, 22000: 0x38F260C, 23000: 0x3318530, 24000: 0x31C9AD0,
    25000: 0x37D4714, 26000: 0x381BDDC,
}
OPERATION_FIELDS = {
    1000: {"lotteryId", "limitedLotteryTickets", "lotteryTicketId", "userPC", "stock", "id"},
    2000: {"UserGift", "id", "contents", "itemId", "amount"},
    3000: {"userDungeonTicket", "dungeonTicketId", "gamelibConsume", "acquireAmount"},
    5000: {"quest", "id", "questReward"},
    18000: {"GiveItems", "itemId", "amount", "missionId", "stageId"},
    21000: {"UserGift", "id", "contents", "itemId", "amount", "missionIds"},
    22000: {"UserGift", "id", "contents", "itemId", "amount", "levelIds"},
    23000: {"UserGift", "id", "contents", "itemId", "amount", "scoreAttackRewardIds"},
    24000: {"discovery", "stamp", "itemId", "amount", "GiveItems", "IssuedAmount", "UserLotteryTicket",
        "lotteryDt", "slotNo", "step", "stamp_increment"},
    25000: {"limitedLotteryTickets", "lotteryTicketId", "pcCostumeProductId", "count"},
    26000: {"limitedLotteryTickets", "lotteryTicketId", "userPackProduct", "packProductId", "count"},
}

PACKET_OPERATIONS = {
    "battle_rush/reward": 18000, "cat_diary/reward": 24000, "dungeon/complete": None,
    "gift/receive": 2000, "pack_product/acquire": 26000, "pc_costume/acquire": 25000,
    "star_library/level_reward": 22000, "star_library/mission_reward": 21000,
    "star_library/score_attack_reward": 23000,
}

PACKETS = {
    "battle_rush/reward": {
        "request": "stageId, courseId and first-clear missionIds",
        "response": "operation type 18000; GiveItems entries carry itemId, amount, missionId and stageId",
        "server_obligation": "validate stage/course and first-clear missions; persist Battle Rush claim rows; deliver exact rewards once",
    },
    "cat_diary/reward": {
        "request": "lotteryDt, slotNo and step from the selected UserCatDiaryChain",
        "response": "operation type 24000; client consumes the traced Cat Diary reward and progress fields",
        "server_obligation": "validate that exact chain; persist chain/status counters; deliver its weighted original gift once",
    },
    "dungeon/complete": {
        "request": "dungeonId, only from the roguelike completion path",
        "response": "common store only; action callback is empty and no operation handler is linked",
        "server_obligation": "validate a matching active roguelike run; persist its exact completion transition and rewards once",
    },
    "gift/receive": {
        "request": "userId and IDs extracted from actual UserGift rows",
        "response": "operation type 2000 with exact UserGift rows; client applies contents and marks gifts received",
        "server_obligation": "atomically consume each pending gift and materialize every typed content exactly once",
    },
    "pack_product/acquire": {
        "request": "packProductId selected by GemListUIState::openPackConfirm",
        "response": "operation type 26000 with limitedLotteryTickets and userPackProduct",
        "server_obligation": "validate original cost and purchase limit; debit once; persist product count; materialize every typed content",
    },
    "pc_costume/acquire": {
        "request": "pcCostumeProductId selected by GemListUIState::openPCCostumeConfirm",
        "response": "operation type 25000 with limitedLotteryTickets, pcCostumeProductId and count",
        "server_obligation": "validate original cost and purchase limit; debit once; persist product and costume rows",
    },
    "star_library/level_reward": {
        "request": "levelIds whose local state is 1",
        "response": "operation type 22000 creates UserGift; after gift pull the client advances level state 1 to 2",
        "server_obligation": "create each exact original gift once without prematurely claiming the local level row",
    },
    "star_library/mission_reward": {
        "request": "missionIds in state 3 or 4 plus bookId",
        "response": "operation type 21000 creates UserGift; after gift pull the client advances mission state 4 to 5",
        "server_obligation": "atomically advance eligible rows 3 to 4 and create each exact original gift once",
    },
    "star_library/score_attack_reward": {
        "request": "scoreAttackRewardIds whose local state is 1",
        "response": "operation type 23000 creates UserGift; after gift pull the client advances reward state 1 to 2",
        "server_obligation": "create each exact original gift once without prematurely claiming the local reward row",
    },
}


def strings(pc):
    start, size = n.enclosing(pc)
    return {item["text"] for item in trace(start, size)["string_candidates"]}


def has(pc, instruction):
    return instruction in n.disasm(pc, 4)


def main():
    for action in PACKETS:
        actual = [referenced_string(pc) for pc in REQUEST_FIELD_REFERENCES[action]]
        assert actual == REQUEST_FIELDS[action], (action, actual)

    schemas = {}
    for name, (pc, expected) in PARSERS.items():
        actual = strings(pc)
        assert expected <= actual, (name, sorted(expected - actual))
        schemas[name] = sorted(expected)

    common = strings(0x30CB6F8)
    assert {"data", "dataTokens", "UserData::storeJson"} <= common

    assert struct.unpack("<24I", n.readva(0x17045B8, 24 * 4)) == OPERATION_TYPES
    bindings = json.loads(Path(__file__).with_name("operation-bindings.json").read_text())
    assert [int(item["target"], 16) for item in bindings] == list(OPERATION_HANDLERS.values())
    assert len(bindings) == len(OPERATION_HANDLERS)
    handler_fields = {}
    for operation_type, expected in OPERATION_FIELDS.items():
        actual = strings(OPERATION_HANDLERS[operation_type])
        assert expected <= actual, (operation_type, sorted(expected - actual))
        handler_fields[str(operation_type)] = sorted(expected)

    assert {"id", "type", "parameters", "token", "signature"} <= strings(0x2FE575C)
    assert {"id", "verifier"} <= strings(0x2FE6300)
    assert "dones" in strings(0x30D027C) and "id" in strings(0x2FE667C)
    listener = trace(*n.enclosing(0x30E1988))
    submit = trace(*n.enclosing(0x30D00E8))
    assert any(item["target"] == "0x30d027c" for item in listener["branches"])
    assert any(item["target"] == "0x30d00e8" for item in listener["branches"])
    assert any(item["target"] == "0x2fe575c" for item in submit["branches"])

    # Star Library state machines and post-gift-pull claim transitions.
    assert has(0x38F1580, "mov w1, #1") and has(0x38F16D8, "mov w1, #2")
    assert has(0x36F5BC8, "mov w1, #2") and has(0x36F5BF4, "mov w1, #3")
    assert has(0x36F5C40, "mov w1, #4") and has(0x36F9D50, "mov w1, #5")
    assert has(0x3533A30, "mov w1, #1") and has(0x3533A70, "mov w1, #2")
    assert has(0x3318BBC, "ldur x0") and "bl #0x3533a40" in n.disasm(0x3318BC0, 4)

    result = {
        "client": "Another Eden Global 3.17.0 / 699 ARM64",
        "libapp_sha256": "2789c0f6bb570d168a14d836a36a3e3fc372c60c63a8e79730dc9c67bc78a1dc",
        "warning": "A packet is supported only after its server obligation is implemented, persisted and replay-tested.",
        "packets": PACKETS,
        "packet_operations": PACKET_OPERATIONS,
        "operation_envelope": ["id", "type", "parameters", "token", "signature"],
        "operation_acknowledgement": ["id", "verifier"],
        "operation_handlers": {str(kind): hex(address) for kind, address in OPERATION_HANDLERS.items()},
        "operation_handler_fields": handler_fields,
        "operation_redelivery": "user_data/confirm returns pending operations; user_data/push removes them only after dones by id",
        "response_store": "0x30cb6f8",
        "schemas": schemas,
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(f"PASS: pinned request, operation, acknowledgement and state evidence for {len(PACKETS)} required gameplay packets")


if __name__ == "__main__":
    main()
