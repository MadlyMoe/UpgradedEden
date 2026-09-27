"""Inventory exact-build game-server actions that reach the ARM64 request queue."""
from collections import deque
import json
import re
import struct
from pathlib import Path
import native_refs as n

OUT = Path(__file__).with_name('network-action-inventory.json')
QUEUE = 0x3000DA8
STORAGE_KEYS = {'agree_policy/version', 'daily_bonus/ad_received', 'encryption/aes_iv'}
SPECIAL = {
    'user/migration/status': 'Compared inline by the generic request dispatcher at 0x3012b48.',
    'user/game_user_id_for_eu': 'Uses the separate EU bootstrap HTTP path at 0x301c3fc.',
}
OPTIONAL = {
    'card_key/subscription/recovery': 'Only reachable from subscription dungeon-key recovery; subscriptions are not advertised locally.',
}

# A route name is not a protocol implementation.  This table records only the
# request fields recovered from the frozen client and the current audit state;
# a route stays rejected until its response reads, mutation and replay contract
# have also been traced.
REQUEST_FIELDS = {
    'battle/continue': [],
    'battle/subscription/continue': [],
    'battle_rush/reward': ['stageId', 'courseId', 'missionIds'],
    'card_key/subscription/recovery': ['cardKeyType'],
    'cat_diary/reward': ['lotteryDt', 'slotNo', 'step'],
    'dungeon/complete': ['dungeonId'],
    'dungeon/ticket/issue': ['id', 'num'],
    'friends_invitation/common/confirm': ['masterFriendsInvitationId'],
    'friends_invitation/common/initialize': ['masterFriendsInvitationId'],
    'friends_invitation/guest/initialize': ['masterFriendsInvitationId', 'invitationCode'],
    'gift/receive': ['userId', 'giftIds'],
    'incentive/adcolony/issue': [],
    'incentive/battlecontinue/issue': [],
    'incentive/dailybonus/issue': [],
    'incentive/rewardtap/issue': [],
    'incentive/treasurebox/issue': ['id'],
    'lottery/draw': ['id', 'lotteryPCExId', 'lotteryPCExIds', 'lotteryTicketId'],
    'matching_user/game_user_id': [],
    'pack_product/acquire': ['packProductId'],
    'payment_point/history': ['paymentPointCardId', 'pageNo'],
    'pc_costume/acquire': ['pcCostumeProductId'],
    'quest/close': ['id'],
    'serial_code/consume': ['serialCode'],
    'serial_code/user_data/import': ['serialCode'],
    'star_library/level_reward': ['levelIds'],
    'star_library/mission_reward': ['missionIds', 'bookId'],
    'star_library/score_attack_reward': ['scoreAttackRewardIds'],
    'subscription_ticket/detail': ['ticketId', 'condForGettingTickets'],
    'user/game_user_id_for_eu': [],
    'user/login': [],
    'user/migration/confirm': ['userId'],
    'user/migration/reserve': ['userId', 'saveType'],
    'user/migration/status': [],
    'user/migration/status_reset': [],
    'user/update_meta': ['is32bit'],
    'user_data/confirm': [],
    'user_data/delete': [],
    'user_data/pull': ['tables', 'consistentRead', 'recovery'],
    'user_data/push': ['deltas', 'checksums', 'dataTokens', 'operations', 'scripts', 'badges', 'giftIds', 'surplus'],
}

REQUEST_FIELD_REFERENCES = {
    'battle_rush/reward': [0x2312404, 0x2312484, 0x231254C],
    'card_key/subscription/recovery': [0x2B87F10],
    'cat_diary/reward': [0x31CA3F8, 0x31CA43C, 0x31CA484],
    'dungeon/complete': [0x318F4D8],
    'dungeon/ticket/issue': [0x396797C, 0x39679C0],
    'friends_invitation/common/confirm': [0x31C393C],
    'friends_invitation/common/initialize': [0x31C40C0],
    'friends_invitation/guest/initialize': [0x31C4410, 0x31C445C],
    'gift/receive': [0x373E374, 0x373E3B4],
    'incentive/treasurebox/issue': [0x2CCD530],
    'lottery/draw': [0x34F4018, 0x34F4064, 0x34F40A0, 0x34F40E0],
    'pack_product/acquire': [0x2F7D408],
    'payment_point/history': [0x310B8DC, 0x310B920],
    'pc_costume/acquire': [0x2F7B96C],
    'quest/close': [0x37AF5B4],
    'serial_code/consume': [0x2D4E008],
    'serial_code/user_data/import': [0x2D4B46C],
    'star_library/level_reward': [0x38F22E4],
    'star_library/mission_reward': [0x36F93D8, 0x36F9420],
    'star_library/score_attack_reward': [0x331824C],
    'subscription_ticket/detail': [0x371ECD8, 0x371ED20],
    'user/migration/confirm': [0x2D6158C],
    'user/migration/reserve': [0x335F9E0, 0x335FA24],
    'user/update_meta': [0x34A532C],
    'user_data/pull': [0x30CA278, 0x30CA2C0, 0x30CA308],
    'user_data/push': [0x30C85AC, 0x30C85EC, 0x30C862C, 0x30C866C,
                       0x30C86AC, 0x30C86EC, 0x30C872C, 0x30C876C],
}

REQUIRED_UNTRACED = {
    'battle_rush/reward', 'cat_diary/reward', 'dungeon/complete', 'gift/receive',
    'pack_product/acquire', 'pc_costume/acquire', 'star_library/level_reward',
    'star_library/mission_reward', 'star_library/score_attack_reward',
}
PARTIAL = {'quest/close'}
NON_STUB = {
    'battle/continue', 'dungeon/ticket/issue', 'lottery/draw',
    'matching_user/game_user_id', 'quest/close', 'user/game_user_id_for_eu',
    'user/login', 'user/migration/status', 'user/migration/status_reset',
    'user/update_meta', 'user_data/confirm', 'user_data/pull', 'user_data/push',
}
EXCLUDED = {
    'battle/subscription/continue': 'subscription service is not advertised',
    'card_key/subscription/recovery': 'subscription service is not advertised',
    'friends_invitation/common/confirm': 'publisher social service is outside local single-player play',
    'friends_invitation/common/initialize': 'publisher social service is outside local single-player play',
    'friends_invitation/guest/initialize': 'publisher social service is outside local single-player play',
    'incentive/adcolony/issue': 'advertising service is not advertised',
    'incentive/battlecontinue/issue': 'advertising service is not advertised',
    'incentive/dailybonus/issue': 'advertising service is not advertised',
    'incentive/rewardtap/issue': 'advertising service is not advertised',
    'incentive/treasurebox/issue': 'advertising service is not advertised',
    'payment_point/history': 'publisher payment history is not needed by local storage',
    'serial_code/consume': 'publisher serial-code service is not locally reproducible',
    'serial_code/user_data/import': 'publisher serial-code service is not locally reproducible',
    'subscription_ticket/detail': 'subscription service is not advertised',
    'user/migration/confirm': 'account migration is replaced by local profile storage',
    'user/migration/reserve': 'account migration is replaced by local profile storage',
    'user_data/delete': 'profile deletion is owned by the local profile manager',
}

COMMON_USER_DATA = 'common listener 0x30e1988 stores response data/dataTokens through UserData::storeJson 0x30cb6f8'
RESPONSE_CONTRACTS = {
    'battle/continue': 'action callback reads no JSON fields; billing refresh is invoked at 0x39673a8',
    'battle_rush/reward': f'{COMMON_USER_DATA}; wrapper 0x2313c44 reads no action-specific JSON fields',
    'cat_diary/reward': f'{COMMON_USER_DATA}; wrapper 0x31cbad4 and caller callback 0x2a1e8a8 read no action-specific JSON fields',
    'dungeon/complete': f'{COMMON_USER_DATA}; call site 0x3277094 supplies an empty callback',
    'dungeon/ticket/issue': 'callback 0x3967c40 reads userDungeonTicket.dungeonTicketId and gamelibConsume.acquireAmount',
    'gift/receive': f'{COMMON_USER_DATA}; wrapper 0x3744444 reads no action-specific JSON fields',
    'lottery/draw': 'callback reads userPC[].stock.id',
    'matching_user/game_user_id': 'captured response supplies game_user_id and aesIv',
    'pack_product/acquire': f'{COMMON_USER_DATA}; wrapper 0x2f7d86c reads no action-specific JSON fields',
    'pc_costume/acquire': f'{COMMON_USER_DATA}; wrapper 0x2f7bdd4 reads no action-specific JSON fields',
    'quest/close': f'{COMMON_USER_DATA}; callback 0x37b60c4 reads no action-specific fields and refreshes billing',
    'star_library/level_reward': f'{COMMON_USER_DATA}; wrapper 0x38f3290 reads no action-specific JSON fields',
    'star_library/mission_reward': f'{COMMON_USER_DATA}; callback 0x2c4973c reads stored UserGift.senderId, not response JSON',
    'star_library/score_attack_reward': f'{COMMON_USER_DATA}; callback 0x2c4aa5c reads stored UserGift.senderId, not response JSON',
    'user/game_user_id_for_eu': 'captured bootstrap response supplies game_user_id',
    'user/login': 'captured login response; UserStatus is consumed before profile pull',
    'user/migration/status': 'inline dispatcher reads status; local terminal state is status=0',
    'user/migration/status_reset': 'callback 0x34999e4 branches on success/failure and reads no response body fields',
    'user/update_meta': 'captured response code=0; no durable state mutation',
    'user_data/confirm': 'captured JSON operation/done acknowledgement shape',
    'user_data/pull': 'MessagePack data/dataTokens profile payload consumed by 0x30ca580',
    'user_data/push': 'JSON operation/done acknowledgement plus refreshed tokens consumed by 0x30e1988',
}
STATE_CONTRACTS = {
    'battle/continue': 'atomically debit exact master consume cost; replay must not debit twice',
    'battle_rush/reward': 'UNTRACED: exact UserBattleRush claim rows and reward delivery remain to be recovered',
    'cat_diary/reward': 'UNTRACED: exact UserCatDiary claim counters and reward delivery remain to be recovered',
    'dungeon/complete': 'UNTRACED: exact roguelike UserDungeon completion transition and rewards remain to be recovered',
    'dungeon/ticket/issue': 'atomically debit exact consume cost and increase the selected UserDungeonTicket amount',
    'gift/receive': 'UNTRACED: atomically mark each UserGift claimed and materialize every typed content row exactly once',
    'lottery/draw': 'atomically debit banner cost or ticket and persist draw progress; replay must not draw twice',
    'matching_user/game_user_id': 'issue fixed local identity and IV; no profile mutation',
    'pack_product/acquire': 'UNTRACED: exact UserPackProduct entitlement and typed contents remain to be recovered',
    'pc_costume/acquire': 'UNTRACED: exact UserPCCostumeProduct/UserPCCostume mutation and typed contents remain to be recovered',
    'quest/close': 'PARTIAL: state 4 to 5 and exact gem-only reward are atomic; non-gem rewards are rejected',
    'star_library/level_reward': 'UNTRACED: exact UserStarLibraryLevel claim state and UserGift creation remain to be recovered',
    'star_library/mission_reward': 'UNTRACED: exact mission claim state and UserGift creation remain to be recovered',
    'star_library/score_attack_reward': 'UNTRACED: exact score claim state and UserGift creation remain to be recovered',
    'user/game_user_id_for_eu': 'return fixed local identity; no profile mutation',
    'user/login': 'create/reuse bounded local capability without importing official credentials',
    'user/migration/status': 'report no pending publisher migration; no migration state exists locally',
    'user/migration/status_reset': 'clear only the client startup migration check; no profile migration',
    'user/update_meta': 'validate client metadata; no durable profile mutation',
    'user_data/confirm': 'advance ordered queue state only after durable reply persistence',
    'user_data/pull': 'read the committed profile snapshot without mutation',
    'user_data/push': 'validate and atomically commit authenticated table deltas/tokens; exact replay returns the stored reply',
}


def referenced_string(reference):
    """Resolve the ADRP/ADD literal used at one exact-build field reference."""
    offset = reference - n.base
    word, = struct.unpack('<I', n.code[offset:offset + 4])
    assert word & 0xFFC00000 == 0x91000000
    register = (word >> 5) & 31
    target_offset = (word >> 10) & 4095
    for distance in range(1, 12):
        previous, = struct.unpack('<I', n.code[offset - distance * 4:offset - distance * 4 + 4])
        if previous & 0x9F000000 == 0x90000000 and previous & 31 == register:
            immediate = ((previous >> 5) & 0x7FFFF) * 4 + ((previous >> 29) & 3)
            if immediate & (1 << 20):
                immediate -= 1 << 21
            page = ((reference - distance * 4) & ~4095) + (immediate << 12)
            return n.readva(page + target_offset, 128).split(b'\0', 1)[0].decode()
    raise AssertionError(f'no ADRP for field reference {reference:x}')


def call_graph():
    graph = {start: set() for start, _ in n.ranges}
    for offset, (word,) in enumerate(struct.iter_unpack('<I', n.code)):
        if word & 0xFC000000 not in (0x14000000, 0x94000000):
            continue
        immediate = word & 0x03FFFFFF
        if immediate & 0x02000000:
            immediate -= 0x04000000
        caller = n.enclosing(n.base + offset * 4)
        target = n.base + offset * 4 + immediate * 4
        if caller and target in graph:
            graph[caller[0]].add(target)
    return graph


def path_to(graph, start, target, max_depth=30):
    pending = deque([(start, [start])])
    seen = {start}
    while pending:
        current, path = pending.popleft()
        if current == target:
            return path
        if len(path) > max_depth:
            continue
        for child in graph.get(current, ()):
            if child not in seen:
                seen.add(child)
                pending.append((child, path + [child]))
    return None


def candidates():
    data = n.elf.get_section_by_name('.rodata').data()
    return sorted({value.decode() for value in data.split(b'\0')
                   if re.fullmatch(rb'[a-z][a-z0-9_]*(?:/[a-z][a-z0-9_]*)+', value)})


def main():
    graph = call_graph()
    found = []
    for ref in n.references(candidates()):
        action = ref['string']
        if action in STORAGE_KEYS or action in SPECIAL or not ref['enclosing']:
            continue
        path = path_to(graph, ref['enclosing'][0], QUEUE)
        if path:
            found.append({
                'action': action,
                'kind': 'queued',
                'string_va': ref['string_va'],
                'reference': ref['reference'],
                'entry_function': hex(ref['enclosing'][0]),
                'call_path': [hex(address) for address in path],
            })
    by_action = {entry['action']: entry for entry in found}
    queued_count = len(by_action)
    for action, evidence in SPECIAL.items():
        by_action[action] = {'action': action, 'kind': 'special', 'evidence': evidence}
    for action, entry in by_action.items():
        entry['local_support'] = 'excluded_subscription' if action in OPTIONAL else 'routed'
        if action in OPTIONAL:
            entry['evidence'] = OPTIONAL[action]
        entry['request_fields'] = REQUEST_FIELDS[action]
        references = REQUEST_FIELD_REFERENCES.get(action, [])
        assert len(references) == len(entry['request_fields'])
        assert [referenced_string(reference) for reference in references] == entry['request_fields']
        entry['request_field_references'] = [hex(reference) for reference in references]
        if action in REQUIRED_UNTRACED:
            entry['requirement'] = 'required_gameplay'
            entry['semantic_status'] = 'untraced_rejected'
        elif action in EXCLUDED:
            entry['requirement'] = 'excluded'
            entry['semantic_status'] = 'not_implemented'
            entry['exclusion_reason'] = EXCLUDED[action]
        elif action in PARTIAL:
            entry['requirement'] = 'required_gameplay'
            entry['semantic_status'] = 'partial_gem_only_rejected_otherwise'
        else:
            entry['requirement'] = 'required_runtime'
            entry['semantic_status'] = 'implemented_non_stub'
        if action in RESPONSE_CONTRACTS:
            entry['response_contract'] = RESPONSE_CONTRACTS[action]
            entry['state_contract'] = STATE_CONTRACTS[action]
    result = {
        'client': 'Another Eden Global 3.17.0 / 699 ARM64',
        'libapp_sha256': '2789c0f6bb570d168a14d836a36a3e3fc372c60c63a8e79730dc9c67bc78a1dc',
        'queue_function': hex(QUEUE),
        'actions': [by_action[name] for name in sorted(by_action)],
    }
    assert queued_count == 37, f'expected 37 queue-backed actions, found {queued_count}'
    assert len(result['actions']) == 39
    assert sum(entry['local_support'] == 'routed' for entry in result['actions']) == 38
    assert set(by_action) == set(REQUEST_FIELDS)
    assert set(by_action) == REQUIRED_UNTRACED | PARTIAL | NON_STUB | set(EXCLUDED)
    assert PARTIAL < NON_STUB
    assert set(RESPONSE_CONTRACTS) == set(STATE_CONTRACTS) == REQUIRED_UNTRACED | NON_STUB
    OUT.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f"{queued_count} queue-backed actions; {len(result['actions'])} total actions")


if __name__ == '__main__':
    main()
