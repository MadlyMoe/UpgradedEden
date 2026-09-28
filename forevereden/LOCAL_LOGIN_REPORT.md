# Local Android login and profile bootstrap: September 26, 2026

## Latest checkpoint and listener command

The non-root Android launcher now captures a complete official profile, sanitizes
it under a fixed local-only identity and starts the separate private package. The
private client accepted local login, the 207-table profile, resource metadata,
`user/migration/status_reset` and bounded atomic gameplay saves. It loaded the
captured checkpoint without a network dialog, completed a quest, crossed into a
new area and persisted subsequent state. Stopping that package and launching the
untouched official package still produced Continue and the same checkpoint. No
account transfer or migration endpoint was used.

From PowerShell, start the listener with:

```powershell
Set-Location 'C:\Main\Productivity\StopKillingGames\Projects\UpgradedEden'
npm run listen
```

Start the ForeverEden MuMu instance first. The command reads its current ADB
address, verifies the launcher and private app, stops any standalone Android
listener, imports the selected User Manager profile and prior state into SQLite,
installs the guest loopback reverse and launches the private client. Permanent resource
preloading uses the private client's own folders, so those files do not need
remounting after a guest restart.
`ANDROID_SERIAL` selects another already-connected device;
`ADB` can override the `adb` executable found on PATH. Without the task MuMu state
file, exactly one connected device is required unless `ANDROID_SERIAL` is set.
No dependency installation is needed. The host listener binds
`http://127.0.0.1:28765`; leave the terminal open and use Ctrl+C to stop it and
remove the reverse. Rerun
the command after restarting MuMu or toggling root.
Connection checks: `node tools/test_forevereden_connect.cjs` and
`python tools/test_forevereden_resources.py`. The private APK now supplies the
same fixed local identity to the SDK and local HTTP/profile layers; no runtime
root or injection is needed.

The on-device server accepts bounded authenticated `user_data/push` envelopes
for any captured profile table with an established row identity. It validates
current tokens, checksums, local identity, ordering, table ownership and row
bounds, then commits every delta atomically and replays the encrypted response
after restart. Token-consuming saves receive fresh nonzero item-token and random-
seed signatures in the original response shape. Live saves now cover roaming,
quest completion, area transition, cat-diary initialization and UI closure.
The listener recognizes 38 exact-build action names, but no longer treats route
recognition as protocol support. Eighteen have non-stub semantics; four necessary
gameplay routes and all excluded service routes fail closed instead of receiving
`code: 0`. Operation-backed routes persist the exact client envelope and require
the matching `{id, verifier}` save acknowledgement before returning `dones`.
Dreams draws spend local Chronos Stones and return actual
3.17.0 `lotteryPCEx` keys in the recovered `userPC[].stock.id` shape. The
runtime carries all 1,334 referenced pools and all 1,682 drawable banner layouts,
including 9+1 and 8+2 guarantees. It preserves each pool's rarity weights and
chooses a profile-owned character inside that rarity so the installed assets can
render the result. Cat Diary reward, roguelike dungeon completion, pack purchase,
costume purchase, publisher migration and deletion remain explicitly unimplemented.

The 2026-09-27 quest-clear reconnect was traced on the retained device state to
save sequence 1267, trigger `StarLibraryUpdateState`: it contained no operations,
but its `UserStarLibraryMissionStatus` rows had no registered composite identity.
After adding `userId` plus `missionId`, the same queued request committed, confirm
and profile pull completed, and the client loaded the dungeon again without a
profile reset.

Original-rule checks now execute **26 isolated ARM64 cases**: ten environment
timer/index cases, three roaming selections, six roaming reset guards and seven
playing-time cases. The current master specifies a 900-second environment
interval and a maximum index of 19 for group 1's first pattern. The captured
8,100-second timestamp advance and index 0 to 9 match the original arithmetic.
Playing time uses a float32 frame accumulator strictly greater than one second,
increments at most once per update, and caps at 2,000,000,000 seconds.

The roaming pool for `571000001` contains `570001030`, `570001031` and
`570001032`, with a 21,600-second respawn interval. The captured destination is
in that pool, but the original reset guard **would retain the living seed row**
with its existing valid destination and `defeatedAt=0`. The actual initialization
or caller state that caused this reset still needs observation. Do not authorize
it merely because its checksum and destination are valid. Clock, property and
RNG inputs in these native tests are controlled fixtures; live clock authority,
random seeding and whole-save authorization remain unproved.

Reproduce this check without writing another decoded master:

```powershell
python data/forevereden-evidence/check_first_save_rules.py
```

The small result is `private-login/first-gameplay-rules-check.json` under the
evidence directory. The shared WSL test helper now removes its temporary package
and fixture directory when the run exits; a subsequent inspection found no
remaining `forevereden-codec-*` directories in `/tmp`.

Passive original capture `official-login/20260926T065843Z` contains four successful
saves: ExplorerScheduled, TreasureGet, AreaChanged and EventDone. Replies contain
trigger names, per-table mutation counts, changed data tokens, and RNG/item-token
updates. Their rule and token-generation authority still needs recovery. These
original replies are evidence, not runtime overlays on the private profile.
The captured TreasureGet uses `3001003001`, whose current original master record
is `treasure.spot.muraosa_closet_2`: one 500-gold entry with raw weight 10000.
It is distinct from the earlier recovered story treasure `3001001001` (50 gold).
This identifies its content; it does not implement the claim or currency signature.
The 67,058-byte PCAP has SHA-256
`8bf92e1c3943441cce644ff11087281a1773ac76d2624ea7b70d3269e1d47bf5`.
The preceding capture `20260926T065719Z` failed in its diagnostic string reader
and is excluded from successful capture evidence.

Focused server tests cover migration authentication, empty-body enforcement,
route ownership, bounded roaming-save validation, replay and restart persistence.
After the user's storage request, eight reproducible files totaling 635,048,923
logical bytes were removed; original/frozen/private APKs, current content and
SQLite remain intact. The listener was then bound successfully, database
integrity checked, and stopped. Cleanup is recorded in
`data/forevereden-evidence/artifact-cleanup-20260926.json`.

The sections below retain the earlier login and identity checkpoints. Their
unsupported-migration and sequence-8 statements are historical, superseded above.

**The separate ForeverEden Android client passes login, accepts local resource
metadata, completes its encrypted profile pull and is playable at the captured
Mayor's House checkpoint on the Surface Pro 11.** The first roaming save is
persisted; unsupported saves continue to fail closed.

## Resource and profile progress

The original first two resource phases contain 89,802 verified assets totaling
4,300,541,601 bytes. With insufficient space for another copy, the private client
uses Android's existing OverlayFS support. A disposable 1 MiB fixture first
proved metadata-only ownership changes and copy-on-write isolation. The native
kernel feature is described in the [Linux OverlayFS documentation](https://docs.kernel.org/filesystems/overlayfs.html#metadata-only-copy-up).

`tools/forevereden_resources.py` verifies both installed APK sets, exact content
generation, source asset hashes, ownership and path boundaries. It mounts only
resource phases 1 and 2; no account/cache/datastore directories are shared.
Original files form the lower layer; separate private upper layers hold changed
metadata and private writes. Initially the layers allocated 424,951,808 bytes;
after native updater manifest writes they allocated 471,592,960 bytes. Every
source resource hash and owner/mode/size remained unchanged. Unmount and remount
passed, including all 89,802 asset hashes read through the remounted private view.

The first native updater attempt found another required boundary: copied
`remoteVersionUrl` fields still pointed at the official asset API, which returned
the literal `invalid session` for the private account. Only the private manifest
copies were corrected. Version and project metadata now come from four bounded,
hash-pinned local GET routes under `/content/<generation>/`. Actual asset bytes
and public CDN URLs remain original. No publisher credentials were reused.

The next real-client run requested local phase-1 version/project metadata and
completed `user/update_meta`, `user_data/confirm` and `user_data/pull` with HTTP 200.
The pull supplied **206 tables / 208 tokens**; UserStatus had already arrived in
login, bringing the starter store to 207 tables. The native client subsequently
rendered New Game. Authentication used the private capability. Queue sequence 2
and `is32bit:0` are committed in SQLite; the original starter gameplay values
remain unchanged there.

New Game requests `user_data/push`. A bounded observer captured its authenticated
1,079,082-byte plaintext request while the normal server still returned 503.
It has ID/sequence `0/3`, one `Blocking` delta, 60 `putItems` tables, no deletions,
no operations and no gift claims. All 60 supplied data tokens match committed
tables; before/after checksums are 32-character hexadecimal strings. This does
not prove their algorithm or the delta signature. Some native output values,
including row user IDs, differ from the imported snapshot. The original public
game ID also differs from its internal account ID. These distinctions must be
traced before accepting saves; no arbitrary client IDs or deltas are committed.

Static tracing now identifies the row-ID change. The original SDK callback at
`0x34a82e0` reads `gamelib::Xuid::xuid()`, parses its decimal value, and saves it
through `0x301c2f4` under `user/user_id`. The save-preparation routine at
`0x30c680c` reads that cached identity and calls `0x3b4981c`, which replaces row
user IDs across the profile. The currency setter at `0x3986b08` marks a changed
ID dirty. This explains why a profile read can produce a large subsequent delta
even without a gameplay action. It is an identity mismatch, not evidence of
MessagePack integer truncation or an anti-cheat failure.

The private server currently provisions its HTTP capability and profile ID,
but has not replaced the earlier SDK identity flow. Changing response headers
alone is insufficient. A local sign-in adaptation must establish the same
server-owned identity throughout SDK-facing state, game state and SQLite.
Do not adopt an SDK-assigned ID into the private database to conceal this gap.
`check_save_identity.py` verifies the pinned original instructions and imported
symbol names; `save-identity-check.json` records their hashes. This is static
evidence, not proof of an offline SDK login or a successful replacement.

### Bounded identity experiment

A subsequent 180-second test temporarily supplied the existing SQLite account
ID to the SDK's native XUID getter **only inside this private client's startup
callback**. Original getters/setters, cached-account change handling and save
preparation then ran normally. The installed APKs were hash-verified and were
not modified. The server's unsupported-save rejection stayed active.

Both the cached-ID setter and save-preparation observer reported the private
ID. A fresh real-client confirm/pull completed at `0/7` and `1/8`. The previous
60-table startup push did not recur during the test, and the title screen
offered **Continue**. Continue requested `user/migration/status_reset`, which
was rejected with 503 and displayed network error 1003. Its route was identified
by matching the logged SHA-256 to the exact string in the original library.
The imported login's `accountMigrationStatus` is already zero; changing that
flag is not an evidenced solution to this new request.

This confirms the ID mismatch causally for this run, but the hook is a diagnostic,
not a shipped sign-in implementation. SDK authentication/network independence
and persistence of a permanent adaptation still need proof. No gameplay save,
migration reset, reward or battle succeeded. SQLite now retains startup sequence
8; gameplay tables remain equal to the imported starter. The earlier sequence-2
verification files describe the preceding uninstrumented run.

Evidence: `check_private_identity_live.py`, `private-login/identity-live-check.json`,
`private-login/live-identity-test.jsonl`, `private-login/identity-test-verification.json`
and `migration-status-reset-trace.json`. All temporary hooks, helper processes,
forwarding and resource mounts were removed after the bounded experiment.

Evidence: `private-resources/mount.json`, `private-resources/routes.json`,
`resource-overlay-check.json`, `private-login/live-local-resources.jsonl`,
`private-login/profile-gate-verification.json` and `private-login/push-envelope-check.json`
beneath `data/forevereden-evidence/`. Raw save capture remains local and ignored.

The original client separately reached its opening story scene after its
completed resource download. No mod loader, gameplay patch or certificate
spoof was needed for either observed path. This does not establish complete
anti-cheat coverage, sleep/resume reliability or Steam compatibility.

## Original traffic and starter provenance

Wireshark was not installed locally. The emulator's existing `tcpdump` produced
a Wireshark-readable PCAP, and bounded temporary native observation hooks
recorded the original game's decoded request and response bodies. The selected
capture is `data/forevereden-evidence/official-login/20260926T045127Z/`.
Its 126,238-byte PCAP has SHA-256
`f2a56b0194b09b294ce7f076da886eb26a786afcee86138846171ffe447b2afd`.
TLS packets alone do not expose these application bodies.

This capture includes one controlled change: the original profile-pull
function received an empty local table-token map, once, to request a full read.
The original code constructed and sent that request with its normal
authentication. No response, authorization check or server gameplay value was
overridden. An earlier passive capture is retained separately. An unsuccessful
capture containing a shell error is also retained and is not counted as PCAP
evidence. All helpers were stopped and emulator Root Access was returned Off.

| Action | Captured request | Captured response |
|---|---|---|
| `matching_user/game_user_id` | Empty; ID/sequence `0/0` | JSON: result code, game user ID, AES IV |
| `user/login` | Empty; `0/0` | JSON: configuration, UserStatus, token, AES IV |
| `user/update_meta` | `{"is32bit":0}`; `0/0` | JSON `{"code":0}` |
| `user_data/confirm` | Empty; `0/11` in this capture | JSON: dataTokens, migrators, operations |
| `user_data/pull` | 207 table names, `consistentRead:false`, `recovery:false`; `1/12` | `application/x-msgpack`: data, dataTokens, recovery |

The starter snapshot contains 207 data tables and 209 table tokens. `ItemTokens`
and `RandomSeeds` are aliases for `UserItemToken` and `UserRandomSeed`. This is
the observed account before its first battle, after several test logins; it is
not claimed to be a pristine first-login default. Private import replaces user
IDs and database row IDs and generates a new local capability/IV. It excludes
the original pending operation queue and all official HTTP session credentials.
Original numeric gameplay state is retained. Raw capture and import artifacts
remain Git-ignored and local.

## Non-root Android capture launcher

`android/forevereden-launcher` now captures the same startup profile on an
ordinary Android device. The launcher requests Android's standard VPN consent,
exports its capture CA to Downloads, and opens Android's CA installer for the
required one-time platform consent. Its `VpnService` then routes only
`games.wfs.anothereden` and only the resolved IPv4 addresses for
`api-us.another-eden.games` to a loopback TLS bridge. The launcher owns the VPN,
listener and User Manager files; capture does not use `su`, ADB, Frida or a
cloned game package. The user-installed CA is a device trust anchor until the
user removes it in Android's trusted-credentials settings.

The bridge forwards ordinary requests and preserves the original KMS response
headers. On the first confirm it clears the in-memory table-token map once, so
the unmodified client constructs, signs and sends its normal full-profile pull.
The bridge writes a profile only when the result has exactly 207 data tables and
the two observed token aliases. The saved JSON replaces account and row identities
with the fixed local-only identity, removes the official AES IV and session tokens,
and redirects service URLs to the on-device server. No account-transfer or
migration endpoint is called.

The focused test drives the real local HTTPS bridge with captured encrypted
fixtures. On MuMuPlayerARM, the installed launcher established `tun0` with the
launcher as owner, the original package as its only allowed UID, only the official
API IPv4 routes, and a listener at `127.0.0.1:28764`. A live non-root capture then
exported the complete sanitized profile into User Manager and stopped the VPN.
The original account remained playable afterward. IPv6-only networks are not
yet supported.

## What is implemented

`tools/forevereden_mobile_server.cjs` is the active listener used by both the
Android launcher button and `npm run listen`. It uses Node's built-in HTTP,
crypto and zlib APIs. `tools/forevereden_transport.cjs` implements the verified
body codec and bounded MessagePack encoder. The older host SQLite server remains
a tested diagnostic implementation and now shares the same save transaction rules.

The on-device launcher stores each selected User Manager profile beside an atomic
JSON state file containing its private
identity/capability, table overrides and replay records. A later launch does not
overlay a new capture onto that state. Each accepted save and its reply commit
together; unsupported specialized routes, including battle, purchases and gift
claims, return an error.

The server binds only `127.0.0.1:28765`. It caps connection count, headers,
request bodies, decoded data and stored queued replies. Seven startup/profile/save
routes are implemented. API URLs returned to the private client stay local;
public content CDN URLs remain original. Third-party URLs embedded elsewhere
in the APK have not all been redirected, so complete network isolation is
not claimed.

The three bootstrap actions reuse `0/0`, including across cold starts. They
are idempotent reads or a metadata replacement, not queued replay identities.
The two `user_data` routes use checked monotonic sequences and exact cached
replies for retries. Global sequence enforcement on bootstrap calls was an
implementation error found by live testing and corrected without resetting
the profile. Database backups precede runtime rebindings.

The response checksum header is MD5 of the **request plaintext**, not of the
response. Both game-ID and login responses use the embedded fallback IV;
later responses use the IV returned by login. Five captured encrypted
responses decode byte-for-byte with the implementation.

## Authentication and evidence limits

The SDK starts with no one-time token, even after a cold restart at this stage.
`--enroll` explicitly opens a **local-only bootstrap pairing window** for
game-ID/login calls. Device metadata limits accidental mismatches; it is not
an authenticator. With pairing disabled, those unauthenticated requests fail
401. Profile/metadata routes require the generated private capability, user ID
and consistent device metadata even while pairing is enabled.

This is deliberately a single local account experiment. It does not implement
the original publisher authentication or a remotely deployable account system.
Secure unattended cold-start credential provision remains a separate task.
Do not expose this pairing mode through a network tunnel or external listener.

| Check | Result / practical limit |
|---|---|
| Original wire/body codec | 17 original native framing fixtures and five captured encrypted replies pass |
| Profile serializer | All 207 captured table values survive MessagePack encode/decode comparison |
| Server behavior | Real HTTP tests cover capability rejection, bootstrap `0/0` reuse, bounded parsing, profile pull, stale/conflicting retries, exact duplicate replies, rollback and restart |
| Live private client | Local game-ID/login, resource metadata, metadata update, confirm and profile pull accepted; New Game rendered |
| Restart | Same account remains after client/server restart with explicit pairing enabled; pairing-disabled bootstrap correctly rejects |
| Actual Android profile pull | Encrypted 206-table pull completed; the next Blocking save exposes unresolved native value normalization; full profile semantic correctness is not claimed |
| Gameplay/save/reward | Unsupported; no fabricated success handlers |
| Original app | Original package/data preserved; opening story scene rendered separately |

## Reproduce the local login

From the repository root, with the existing task emulator running:

```powershell
$adbPath = 'C:\Main\Productivity\Coding\Android\Sdk\platform-tools\adb.exe'
$instanceState = Get-Content -Raw 'C:\Program Files\Netease\MuMuPlayerARM\vms\vm2.gmadoa\misc\state.json' | ConvertFrom-Json
$deviceSerial = '{0}:{1}' -f $instanceState.AdbHost,$instanceState.AdbPort
& $adbPath connect $deviceSerial
```

For a one-time permanent resource preload, temporarily enable Root Access in
**this task emulator** and stop both game packages. If the old temporary resource
views are mounted, unmount them first using `forevereden_resources.py unmount`.
The following command copies only hash-matching original assets into the private
folders and downloads missing assets from their pinned CDN URLs. Each batch is
verified before publication; the original files and account data stay unchanged.

```powershell
& $adbPath -s $deviceSerial shell am force-stop games.wfs.anothereden
& $adbPath -s $deviceSerial shell am force-stop games.fed.anothereden
python tools/android_preseed.py --private --adb $adbPath --serial $deviceSerial --manifest-dir data/forevereden-evidence/android-download-before --reserve-gib 3
python tools/forevereden_resources.py route --permanent --adb $adbPath --serial $deviceSerial --phases 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16
```

Publishing a different set of resource routes requires the stopped-server runtime
rebind described below. Return Root Access Off before launching. Then run
`npm run listen`, which starts the host SQLite listener after that toggle. Permanent
private assets survive guest restarts without root or overlay mounts. The older
metadata-only overlay method remains available for low-storage diagnostic setups;
do not mount it over the permanent preload. The current guest is SELinux
permissive; these tests do not establish support on an enforcing physical device.

```powershell
python tools/forevereden_probe.py verify
node tools/test_forevereden_server.cjs
python tools/test_forevereden_resources.py
python data/forevereden-evidence/check_save_identity.py
npm run listen
```

The command opens the already installed **ForeverEden** app after readiness. Do
not reinstall or clear its data. The selected on-device Node runtime is ARM64;
the legacy host verification uses Node 24.13.1 and its built-in SQLite API.
Preparation uses the already installed Python
environment's bundled MessagePack reader. No dependency was installed.

To republish after a server-source change, stop the server and run:

```powershell
python tools/prepare_forevereden_login.py --capture data/forevereden-evidence/official-login/20260926T045127Z --migrate-database
node tools/test_forevereden_server.cjs
```

This migration only supports the current startup database schema and the
unchanged imported seed. It refuses a mismatched identity or replacing a prior
backup. It is not a general migration framework.

## Next gate

Resource and wire acceptance are now demonstrated. First unify the private
SDK-facing and server identities, then recover the first Blocking save's exact
field conversions, checksum and signature construction before implementing its
transaction and acknowledgement.
The identity experiment also exposes `user/migration/status_reset` as the next
reachable startup operation; recover its request, server state and retry contract
before implementing a terminal response.
Then verify restart with that committed result through the real client.

Then recover one complete original save operation, verify a persistent first
area, and continue the existing one-battle/one-treasure roadmap. Steam follows
that Android slice; a Windows anti-cheat-driver port is not required for the
current Android path.

Evidence includes `private-login/download-prompt.png`,
`private-login/restart-download-prompt.png`, `private-login/verification.json`,
`private-login/live-restart.jsonl`, the preserved SQLite backups, and
`private-login/code-update.json`, all beneath the ignored evidence directory.
`local-runtime-identity.json` binds server code, seed, body-codec inputs,
private client and current content generation.

The latest verification left `npm run listen` running with no ADB reverse and
ADB Root Access Off. The installed private client, resource layers, database and
original client/cache remain intact. Host free space fell to zero during an
earlier investigation.
Seven failed-build APK files were compared member-by-member with the retained
published APKs, then individually hash-checked and removed without recursive
deletion, recovering about 0.55 GB of physical space. Sustained runtime testing
still needs more free host storage; no second resource download was started.
